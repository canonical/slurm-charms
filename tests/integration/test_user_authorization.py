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

"""BDD step definitions for Slurm user authorization tests."""

import pytest
from constants import SLURMD_APP_NAME
from jubilant import Task, TaskError
from pytest_bdd import given, parsers, scenarios, then
from pytest_jubilant_bdd import Context
from utils import assert_command_denied, exec_as_user

pytestmark = pytest.mark.order(7)

scenarios("features/slurm_user_authorization.feature")


@given(
    parsers.re(
        r"a (?i:slurm) job is submitted from unit '(?P<unit>[^']+)' "
        r"as user '(?P<user>[^']+)'"
    )
)
def submit_job_as_user(context: Context, unit: str, user: str) -> None:
    """Submit a sleeping batch job as an unprivileged user and record its job id."""
    juju = context.get_juju()
    result = juju.exec(
        f"sudo -u {user} sbatch --chdir=/tmp --partition {SLURMD_APP_NAME} --wrap 'sleep 30'",
        unit=unit,
    )
    assert result.success, (
        f"failed to submit a job as '{user}' on '{unit}': {result.stderr.strip()}"
    )
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
    try:
        context.wait(ready=ready, successes=1)
    except TimeoutError:
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
    """Assert an unprivileged user's srun job executes under their own identity."""
    command = f"srun --chdir=/tmp --partition {SLURMD_APP_NAME} id -un"

    def attempt() -> Task | None:
        """Run the job once; return the failed Task, or None if it ran as the user."""
        result = exec_as_user(context, command, unit, user, wait=120)
        if result.success and result.stdout.strip() == user:
            return None
        return result

    def ran_as_user(_ctx: Context) -> bool:
        try:
            return attempt() is None
        except Exception:
            return False

    try:
        context.wait(ready=ran_as_user, successes=1)
    except TimeoutError:
        # One last attempt so the failure message carries the actual result;
        # if it returns None, the job ran as the user after all.
        try:
            failed = attempt()
        except Exception as exc:
            raise AssertionError(
                f"'{command}' as '{user}' on '{unit}' never completed "
                f"(last attempt raised: {exc})"
            ) from None
        if failed is None:
            return
        raise AssertionError(
            f"'{command}' as '{user}' on '{unit}' never ran as that user "
            f"(return_code={failed.return_code}): "
            f"stdout={failed.stdout.strip()!r} stderr={failed.stderr.strip()!r}"
        ) from None


@then(
    parsers.parse(
        "an unauthenticated request to the slurmrestd API from unit '{unit}' "
        "is rejected with status '{code}'"
    )
)
def unauthenticated_api_request_rejected(context: Context, unit: str, code: str) -> None:
    """Assert the Slurm REST API rejects requests that lack a JWT token."""
    juju = context.get_juju()
    address = context.get_unit(unit).public_address
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
