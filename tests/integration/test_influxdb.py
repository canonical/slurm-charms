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

"""BDD step definitions for Slurm InfluxDB task accounting.

Currently skipped because the influxdb charm deployment is broken.
"""

import logging

import pytest
from pytest_bdd import parsers, scenarios, then
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.order(12),
    pytest.mark.skip(reason="influxdb charm deployment is currently broken"),
]

scenarios("features/slurm_influxdb_accounting.feature")


@then(
    parsers.parse("a slurm sstat task accounting job on unit '{unit}' reports '{expected}' task")
)
def task_accounting(context: Context, unit: str, expected: str) -> None:
    """Submit a sleep job via sbatch and verify sstat reports the task count."""
    juju = context.get_juju()

    juju.scp(
        "tests/integration/testdata/sbatch_sleep_job.sh",
        f"ubuntu@{unit}:~/sbatch_sleep_job.sh",
    )
    job_id = juju.exec(
        "sbatch", "--parsable", "/home/ubuntu/sbatch_sleep_job.sh", unit=unit
    ).stdout.strip()

    logger.info("\n%s", juju.exec("squeue", unit=unit).stdout)

    # Give a few seconds for the job to enter the queue and transition to RUNNING.
    import time

    time.sleep(5)

    logger.info("\n%s", juju.exec("squeue", unit=unit).stdout)

    result = juju.exec("sstat", job_id, "--format=NTasks", "--noheader", unit=unit).stdout.strip()
    logger.info("\n%s", result)
    assert int(result) == int(expected)
