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

"""BDD step definitions for Slurm OCI runtime (Apptainer) scheduling."""

import logging
from io import StringIO

import pytest
from constants import SLURMD_APP_NAME
from dotenv import dotenv_values
from pytest_bdd import parsers, scenarios, then
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.order(13)

scenarios("features/slurm_oci_runtime.feature")


@then(
    parsers.parse(
        "a slurm apptainer container job submitted from unit '{login_unit}' "
        "runs on unit '{compute_unit}'"
    )
)
def apptainer_oci_scheduling(context: Context, login_unit: str, compute_unit: str) -> None:
    """Pull an OCI image and run a Slurm job inside an Apptainer container."""
    juju = context.get_juju()

    def apptainer_ready(_ctx: Context) -> bool:
        try:
            juju.exec("apptainer --version", unit=compute_unit)
            return True
        except Exception:
            return False

    context.wait(ready=apptainer_ready)

    juju.exec(
        "apptainer pull /tmp/jammy.sif docker://ghcr.io/charmed-hpc/ubuntu-test:jammy",
        unit=compute_unit,
    )
    result = juju.exec(
        f"cd /tmp; srun -p {SLURMD_APP_NAME} --container=/tmp/jammy.sif cat /etc/os-release",
        unit=login_unit,
    ).stdout.strip()
    env = dotenv_values(stream=StringIO(result))

    assert env["VERSION_CODENAME"] == "jammy"
    assert env["VERSION_ID"] == "22.04"
