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

"""BDD step definitions for Slurm cluster deployment."""

import logging

import pytest
from constants import (
    DEFAULT_SLURM_CHARM_CHANNEL,
    MYSQL_APP_NAME,
    SACKD_APP_NAME,
    SLURMCTLD_APP_NAME,
    SLURMD_APP_NAME,
    SLURMDBD_APP_NAME,
    SLURMRESTD_APP_NAME,
)
from pytest_bdd import given, scenarios
from pytest_jubilant_bdd import Context
from utils import local_charm_path

logger = logging.getLogger(__name__)

# Cross-file ordering: the deploy scenario must run before every other
# feature since subsequent scenarios rely on the deployed cluster.
pytestmark = pytest.mark.order(1)

scenarios("features/slurm_cluster_deployment.feature")


# The charm names differ from the application names (e.g. charm "sackd" is
# deployed as app "login"), and slurmctld requires constraints and config.
# The built-in ``deploy`` step assumes charm name == app name, so this is a
# legitimate custom step for domain-specific behaviour.
@given("I deploy the slurm reference cluster")
def deploy_slurm_cluster(context: Context, base: str) -> None:
    """Deploy all Slurm charms plus mysql with the legacy configuration."""
    juju = context.get_juju()
    # `context.get_juju()` returns a fresh `Juju` with jubilant's 180s default
    # wait timeout. The legacy `juju` fixture used one hour for the full
    # cluster deploy; mirror that here so deploys don't time out prematurely.
    juju.wait_timeout = 60 * 60

    def _deploy(charm: str, app: str, **kwargs):
        charm_source = local_charm_path(charm)
        channel = DEFAULT_SLURM_CHARM_CHANNEL if isinstance(charm_source, str) else None
        juju.deploy(charm_source, app, base=base, channel=channel, **kwargs)

    juju.model_config({"update-status-hook-interval": "10s"})

    _deploy("sackd", SACKD_APP_NAME)
    _deploy(
        "slurmctld",
        SLURMCTLD_APP_NAME,
        constraints={"virt-type": "virtual-machine"},
        config={"slurm-conf-parameters": "SlurmctldTimeout=10\n"},
    )
    _deploy("slurmd", SLURMD_APP_NAME)
    _deploy("slurmdbd", SLURMDBD_APP_NAME)
    _deploy("slurmrestd", SLURMRESTD_APP_NAME)
    juju.deploy("mysql", MYSQL_APP_NAME)
