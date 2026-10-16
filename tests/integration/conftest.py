#!/usr/bin/env python3
# Copyright 2023-2026 Canonical Ltd.
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

"""Configure Slurm charm integration tests."""

import logging
import shlex
import uuid
from collections.abc import Iterator

import pytest
from aiosmtpd.controller import Controller
from constants import NETWORK_INTERFACE, SLURMD_APP_NAME, SMTP_SERVER_PORT
from jubilant import Task
from pytest_bdd import parsers, then
from pytest_jubilant_bdd import Context
from utils import MailHandler, interface_ipv4

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def smtp_handler() -> Iterator[MailHandler]:
    """Start a local SMTP server capturing Slurm notification emails."""
    handler = MailHandler()
    ip_address = interface_ipv4(NETWORK_INTERFACE)
    controller = Controller(handler, hostname=ip_address, port=SMTP_SERVER_PORT)
    controller.start()
    try:
        yield handler
    finally:
        controller.stop()


@then(
    parsers.parse(
        "a slurm srun job submitted from unit '{login_unit}' runs on unit '{compute_unit}'"
    )
)
def job_submission(context: Context, login_unit: str, compute_unit: str) -> None:
    """Submit a job from the login node and verify it runs on the compute node."""
    juju = context.get_juju()
    slurmd_result = juju.exec("hostname -s", unit=compute_unit)
    completed_jobs: list[str] = []

    def ready(_ctx: Context) -> bool:
        try:
            job_name = f"bdd-{uuid.uuid4().hex[:8]}"
            sackd_result = juju.exec(
                f"srun -J {job_name} --partition {SLURMD_APP_NAME} hostname -s",
                unit=login_unit,
                wait=120,
            )
            if not sackd_result.success:
                logger.debug(
                    "srun job '%s' failed (return_code=%s): stdout='%s', stderr='%s'",
                    job_name,
                    sackd_result.return_code,
                    sackd_result.stdout,
                    sackd_result.stderr,
                )
                return False
            if sackd_result.stdout != slurmd_result.stdout:
                logger.debug(
                    "srun job '%s' output mismatch: srun stdout='%s', slurmd hostname='%s'",
                    job_name,
                    sackd_result.stdout,
                    slurmd_result.stdout,
                )
                return False
            completed_jobs.append(job_name)
            return True
        except Exception as exc:
            logger.debug("srun job attempt raised exception: %s", exc)
            return False

    context.wait(ready=ready, timeout=600)

    for job_name in completed_jobs[-3:]:
        sacct_result = juju.exec(
            f"sacct --name={job_name} --format=State --noheader --parsable2",
            unit=login_unit,
        )
        assert sacct_result.success
        states = [s.strip() for s in sacct_result.stdout.strip().splitlines() if s.strip()]
        assert states, f"no sacct record found for job '{job_name}'"
        assert any("COMPLETED" in s for s in states), (
            f"job '{job_name}' did not complete, states: {states}"
        )


# ---------------------------------------------------------------------------
# Unprivileged-user command probes (shared by the security features)
# ---------------------------------------------------------------------------

# Output fragments that indicate an authorization denial.
_DENIAL_PATTERNS = (
    "permission denied",
    "access denied",
    "operation not permitted",
    "not permitted",
    "unauthorized",
    "invalid user",
    "must be root",
    "only user root",
    "only the root",
    "superuser",
    "super user",
    "insufficient privilege",
    "authentication required",
    "authentication is required",
)

# Output fragments that indicate the probe itself is broken (missing binary
# or file) rather than denied. A denial scenario must never pass on these.
_VACUOUS_PATTERNS = (
    "command not found",
    "no such file or directory",
    "usage:",
)


def _exec_as_user(context: Context, command: str, unit: str, user: str) -> Task:
    """Execute a command on a unit as an unprivileged user via sudo."""
    juju = context.get_juju()
    return juju.exec(f"sudo -u {user} sh -c {shlex.quote(command)}", unit=unit)


@then(parsers.parse("the command '{command}' on unit '{unit}' as user '{user}' succeeds"))
def command_as_user_succeeds(context: Context, command: str, unit: str, user: str) -> None:
    """Assert a command run as an unprivileged user exits successfully."""
    result = _exec_as_user(context, command, unit, user)
    assert result.success, (
        f"'{command}' as '{user}' on '{unit}' failed "
        f"(rc={result.return_code}): {result.stderr.strip()}"
    )


@then(parsers.parse("the command '{command}' on unit '{unit}' as user '{user}' is denied"))
def command_as_user_is_denied(context: Context, command: str, unit: str, user: str) -> None:
    """Assert a command run as an unprivileged user is rejected on authorization grounds.

    A nonzero exit alone proves nothing: a missing binary or absent file
    also exits nonzero. Require a recognizable denial message and reject
    the known vacuous failures, failing loudly with the observed output.
    """
    result = _exec_as_user(context, command, unit, user)
    output = f"{result.stdout}\n{result.stderr}".lower()
    assert not result.success, (
        f"'{command}' as '{user}' on '{unit}' succeeded, expected denial: {result.stdout.strip()}"
    )
    assert not any(pattern in output for pattern in _VACUOUS_PATTERNS), (
        f"'{command}' as '{user}' on '{unit}' failed for a non-authorization reason "
        f"(broken probe, not a denial): {output.strip()}"
    )
    assert any(pattern in output for pattern in _DENIAL_PATTERNS), (
        f"'{command}' as '{user}' on '{unit}' failed without a recognizable "
        f"denial message: {output.strip()}"
    )


@then(
    parsers.parse(
        "the output of '{command}' on unit '{unit}' as user '{user}' contains '{expected}'"
    )
)
def output_as_user_contains(
    context: Context, command: str, unit: str, user: str, expected: str
) -> None:
    """Assert the output of a command run as an unprivileged user contains text.

    The exit code is deliberately not asserted: probes such as `grep -c`
    legitimately exit nonzero while printing the expected output.
    """
    result = _exec_as_user(context, command, unit, user)
    output = f"{result.stdout}\n{result.stderr}"
    assert expected in output, (
        f"expected '{expected}' in output of '{command}' as '{user}' on '{unit}', "
        f"got: {output.strip()}"
    )


@then(
    parsers.parse(
        "the output of '{command}' on unit '{unit}' as user '{user}' does not contain "
        "'{unexpected}'"
    )
)
def output_as_user_does_not_contain(
    context: Context, command: str, unit: str, user: str, unexpected: str
) -> None:
    """Assert the output of a command run as an unprivileged user lacks text.

    The command must succeed: an absent string in the output of a failed
    command proves nothing.
    """
    result = _exec_as_user(context, command, unit, user)
    assert result.success, (
        f"'{command}' as '{user}' on '{unit}' failed "
        f"(rc={result.return_code}): {result.stderr.strip()}"
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert unexpected not in output, (
        f"unexpected '{unexpected}' in output of '{command}' as '{user}' on '{unit}': "
        f"{output.strip()}"
    )


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--run-high-availability",
        action="store_true",
        default=False,
        help="run high availability tests (slow)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "high_availability: marks tests for slurmctld high availability"
    )
    config.addinivalue_line("markers", "security: gherkinator test type classification")
    config.addinivalue_line("markers", "planned: gherkinator test status classification")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-high-availability"):
        # Flag given in cli: do not skip tests
        return
    skip_ha = pytest.mark.skip(reason="need --run-high-availability option to run")
    for item in items:
        if "high_availability" in item.keywords:
            item.add_marker(skip_ha)
