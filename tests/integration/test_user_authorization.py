#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
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

"""BDD step definitions for Slurm user authorization tests.

The shared unprivileged-user probe steps live in `conftest.py`.
"""

import pytest
from constants import SLURMD_APP_NAME, SLURMRESTD_APP_NAME
from jubilant import Task, TaskError
from pytest_bdd import given, parsers, scenarios, then
from pytest_jubilant_bdd import Context
from utils import assert_command_denied, exec_as_user

pytestmark = pytest.mark.order(7)

scenarios("features/slurm_user_authorization.feature")


@given(parsers.parse("a slurm job is submitted from unit '{unit}' as user '{user}'"))
def submit_job_as_user(context: Context, unit: str, user: str) -> None:
    """Submit a sleeping batch job as an unprivileged user and record its job id.

    Root cannot submit Slurm jobs, so the victim job must be owned by a
    regular user; `sbatch --wrap` keeps it scriptless and long-running.
    `--chdir` is required: `juju exec` runs with a root-owned working
    directory, and without an accessible one the job dies at launch as the
    unprivileged user and never reaches RUNNING.
    """
    juju = context.get_juju()
    result = juju.exec(
        f"sudo -u {user} sbatch --chdir=/tmp --partition {SLURMD_APP_NAME} --wrap 'sleep 30'",
        unit=unit,
    )
    assert result.success, (
        f"failed to submit a job as '{user}' on '{unit}': {result.stderr.strip()}"
    )
    # sbatch prints "Submitted batch job <id>" on success.
    prefix = "Submitted batch job"
    stdout = result.stdout.strip()
    assert prefix in stdout, f"unexpected sbatch output on '{unit}': {stdout}"
    context.scenario_state["job_id"] = stdout.split()[-1]
    context.scenario_state["submit_unit"] = unit


@then(parsers.parse("the submitted job cannot be cancelled by user '{user}' from unit '{unit}'"))
def submitted_job_cancel_denied(context: Context, unit: str, user: str) -> None:
    """Assert an unprivileged user cannot cancel another user's submitted job."""
    job_id = context.scenario_state["job_id"]
    command = f"scancel {job_id}"
    result = exec_as_user(context, command, unit, user)
    assert_command_denied(result, command, unit, user)


@then(parsers.parse("the submitted job is still running"))
def submitted_job_still_running(context: Context) -> None:
    """Poll until the submitted job shows up as RUNNING in the queue."""
    juju = context.get_juju()
    job_id = context.scenario_state["job_id"]
    unit = context.scenario_state["submit_unit"]

    def ready(_ctx: Context) -> bool:
        try:
            result = juju.exec(f"squeue --job={job_id} --noheader --format=%T", unit=unit)
        except Exception:
            return False
        return result.success and "RUNNING" in result.stdout

    # A single RUNNING sighting proves the job survived the denied scancel.
    # The default of 3 consecutive successes can outlast the job's short
    # sleep window when each `juju.exec` round trip takes seconds.
    try:
        context.wait(ready=ready, successes=1)
    except TimeoutError:
        # Surface why the job never ran (pending reason, launch failure,
        # ...) instead of a bare TimeoutError. `scontrol` covers jobs still
        # in the queue, `sacct` jobs that already left it.
        try:
            diagnostics = juju.exec(
                f"scontrol show job {job_id} || "
                f"sacct -j {job_id} --noheader --format=JobID,State,ExitCode",
                unit=unit,
            )
        except TaskError as exc:
            diagnostics = exc.task
        raise AssertionError(
            f"job {job_id} never reached RUNNING:\n"
            f"{diagnostics.stdout.strip()}\n{diagnostics.stderr.strip()}"
        ) from None


@then(parsers.parse("a job run from unit '{unit}' as user '{user}' executes as that user"))
def job_run_executes_as_user(context: Context, unit: str, user: str) -> None:
    """Assert an unprivileged user's srun job executes under their own identity.

    Positive control for the ``--uid`` denial probe. Retried: ``srun``
    fails transiently while ``slurmctld`` restarts after relation events.
    """
    command = f"srun --chdir=/tmp --partition {SLURMD_APP_NAME} id -un"
    last: Task | None = None

    def ready(_ctx: Context) -> bool:
        nonlocal last
        try:
            last = exec_as_user(context, command, unit, user, wait=120)
        except Exception:
            return False
        return last.success and last.stdout.strip() == user

    try:
        context.wait(ready=ready, successes=1)
    except TimeoutError:
        if last is None:
            raise AssertionError(
                f"'{command}' as '{user}' on '{unit}' never completed: every attempt raised"
            ) from None
        raise AssertionError(
            f"'{command}' as '{user}' on '{unit}' never ran as that user "
            f"(return_code={last.return_code}): "
            f"stdout={last.stdout.strip()!r} stderr={last.stderr.strip()!r}"
        ) from None


@then(
    parsers.parse(
        "an unauthenticated request to the slurmrestd API from unit '{unit}' "
        "is rejected with status '{code}'"
    )
)
def unauthenticated_api_request_rejected(context: Context, unit: str, code: str) -> None:
    """Assert the Slurm REST API rejects requests that lack a JWT token.

    Mirrors the authenticated probe in `test_key_rotation.py` but omits
    the `X-SLURM-USER-TOKEN` header; the unversioned `/openapi` path
    requires no version prefix and is auth-gated like every other
    endpoint.
    """
    juju = context.get_juju()
    address = juju.status().apps[SLURMRESTD_APP_NAME].units[unit].public_address
    url = f"http://{address}:6820/openapi"
    result = juju.exec(
        f"curl --silent --show-error"
        f" --write-out '\\nHTTP_RESPONSE_CODE:%{{http_code}}'"
        f" --request GET '{url}'",
        unit=unit,
    )
    assert "HTTP_RESPONSE_CODE:" in result.stdout, (
        f"no status code in response, stdout: {result.stdout} stderr: {result.stderr}"
    )
    _, status_line = result.stdout.strip().rsplit("HTTP_RESPONSE_CODE:", 1)
    actual = status_line.strip()
    assert actual == code, (
        f"unauthenticated request to slurmrestd from '{unit}' got HTTP {actual}, expected {code}"
    )
