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

"""Configure Slurm charm integration tests."""

import logging
import uuid
from collections.abc import Iterator

import pytest
from aiosmtpd.controller import Controller
from constants import NETWORK_INTERFACE, SLURMD_APP_NAME, SMTP_SERVER_PORT
from pytest_bdd import parsers, then
from pytest_jubilant_bdd import Context
from utils import MailHandler, interface_ipv4

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def base(request: pytest.FixtureRequest) -> str:
    """Get the base to deploy the Slurm charms on."""
    return request.config.getoption("--charm-base")


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


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--charm-base",
        action="store",
        default="ubuntu@26.04",
        help="the base to deploy the slurm charms on during the integration tests",
    )
    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="keep temporarily created models",
    )
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
    if config.getoption("--keep-models"):
        # pytest-jubilant-bdd owns model teardown and only honors its own
        # `--juju-bdd-no-teardown` flag, so forward `--keep-models` to it.
        config.option.juju_bdd_no_teardown = True


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-high-availability"):
        # Flag given in cli: do not skip tests
        return
    skip_ha = pytest.mark.skip(reason="need --run-high-availability option to run")
    for item in items:
        if "high_availability" in item.keywords:
            item.add_marker(skip_ha)
