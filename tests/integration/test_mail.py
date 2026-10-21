# Copyright 2024-2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""BDD step definitions for Slurm mail notifications."""

import logging

import jubilant
import pytest
from constants import SLURMD_APP_NAME, SMTP_INTEGRATOR_APP_NAME
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_jubilant_bdd import Context
from utils import MailHandler, interface_ipv4

logger = logging.getLogger(__name__)

# Order 14: after job submission (12) and oci runtime (13), before HA (19).
pytestmark = pytest.mark.order(14)

scenarios("features/slurm_mail_notifications.feature")


@given(parsers.parse("I deploy 'smtp-integrator' with auto-resolved local host and port '{port}'"))
def deploy_smtp_integrator(context: Context, smtp_handler: MailHandler, port: str) -> None:
    """Deploy ``smtp-integrator`` with the local interface IP and given port."""
    juju = context.get_juju()
    from constants import NETWORK_INTERFACE

    # `smtp_handler` is unused, but requesting it here forces the SMTP capture
    # server to start before any mail-triggering job is submitted. pytest-bdd
    # resolves step fixtures lazily at step execution time, so without this the
    # server would only start when the Then step runs -- after the job has
    # already ended and slurm-mail has attempted delivery.
    juju.deploy(
        "smtp-integrator",
        SMTP_INTEGRATOR_APP_NAME,
        config={"host": interface_ipv4(NETWORK_INTERFACE), "port": int(port)},
    )


@when(
    parsers.re(
        r"I run a (?i:slurm) srun job on unit '(?P<unit>[^']+)' "
        r"with mail user '(?P<to_address>[^']+)' and mail type '(?P<mail_type>[^']+)'"
    )
)
def run_slurm_job_mail(context: Context, unit: str, to_address: str, mail_type: str) -> None:
    """Run an srun job that triggers a Slurm mail notification.

    Retries until the submission succeeds: the plugin's built-in ``I execute``
    step swallows command failures, and ``srun`` can fail transiently while
    ``slurmctld`` restarts after the SMTP integration rewrites ``slurm.conf``.
    A swallowed failure means no job runs and no email is ever sent.
    """
    juju = context.get_juju()

    def ready(_ctx: Context) -> bool:
        try:
            result = juju.exec(
                f"srun --time=1 --partition {SLURMD_APP_NAME} "
                f"--mail-user={to_address} --mail-type={mail_type} sleep 1",
                unit=unit,
                wait=120,
            )
            if not result.success:
                logger.debug(
                    "mail-triggering srun failed (return_code=%s): stdout='%s', stderr='%s'",
                    result.return_code,
                    result.stdout,
                    result.stderr,
                )
                return False
            return True
        except Exception as exc:
            logger.debug("mail-triggering srun raised: %s", exc)
            return False

    context.wait(ready=ready)


@when(
    parsers.re(
        r"I run a failing (?i:slurm) srun job on unit '(?P<unit>[^']+)' "
        r"with mail user '(?P<to_address>[^']+)' and mail type '(?P<mail_type>[^']+)'"
    )
)
def run_failing_slurm_job_mail(
    context: Context, unit: str, to_address: str, mail_type: str
) -> None:
    """Run a failing srun job that triggers a Slurm failure mail notification."""
    juju = context.get_juju()
    try:
        juju.exec(
            f"srun --time=1 --partition {SLURMD_APP_NAME} "
            f"--mail-user={to_address} --mail-type={mail_type} "
            f"bash -c 'sleep 1; exit 1'",
            unit=unit,
        )
    except jubilant.TaskError:
        # Failure is intentional — it triggers the FAIL notification email.
        pass


@then(
    parsers.parse(
        "a notification email is received by '{to_address}' with subject matching '{subject_pattern}' "
        "and content matching '{content_pattern}'"
    )
)
def email_received(
    context: Context,
    smtp_handler: MailHandler,
    to_address: str,
    subject_pattern: str,
    content_pattern: str,
) -> None:
    """Poll the SMTP handler until an email matching the patterns is received."""

    def ready(_ctx: Context) -> bool:
        try:
            smtp_handler.assert_mail(to_address, subject_pattern, content_pattern)
            return True
        except AssertionError as exc:
            logger.debug(
                "waiting for email to '%s' (%s); latest captured email: To='%s', Subject='%s'",
                to_address,
                exc,
                smtp_handler.latest_email["To"],
                smtp_handler.latest_email["Subject"],
            )
            return False

    context.wait(ready=ready)
