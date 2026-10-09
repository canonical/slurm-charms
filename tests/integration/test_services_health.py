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

"""BDD step definitions for Slurm services health checks."""

import logging

import pytest
from constants import SLURM_APPS
from pytest_bdd import parsers, scenarios, then
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.order(2)

scenarios("features/slurm_services_health.feature")


@then("the slurm systemd service is active on all slurm units")
def slurm_services_active(context: Context) -> None:
    """Verify ``systemctl is-active`` returns ``active`` for every Slurm service."""
    juju = context.get_juju()
    status = juju.status()
    for app, service in SLURM_APPS.items():
        for unit in status.apps[app].units:
            result = juju.exec(f"systemctl is-active {service}", unit=unit)
            assert result.stdout.strip() == "active", (
                f"service '{service}' not active on unit '{unit}': {result.stdout.strip()}"
            )


@then(
    parsers.parse(
        "the slurmctld metrics endpoint on unit '{unit}' returns http status '{status_code}'"
    )
)
def metrics_endpoint(context: Context, unit: str, status_code: str) -> None:
    """Curl the prometheus-slurm-exporter metrics endpoint and check the HTTP code."""
    juju = context.get_juju()
    result = juju.exec(
        "curl --silent --output /dev/null --write-out '%{http_code}\\n' localhost:6817/metrics",
        unit=unit,
    )
    assert result.stdout.strip() == status_code, (
        f"metrics endpoint returned '{result.stdout.strip()}', expected '{status_code}'"
    )


@then(parsers.parse("unit '{unit}' is listening on TCP port '{port}'"))
def port_listening(context: Context, unit: str, port: str) -> None:
    """Verify a TCP port is listening using ``lsof``."""
    juju = context.get_juju()
    result = juju.exec("lsof", "-t", "-n", f"-iTCP:{port}", "-sTCP:LISTEN", unit=unit)
    assert result.stdout.strip() != "", f"nothing listening on port {port} on unit '{unit}'"
