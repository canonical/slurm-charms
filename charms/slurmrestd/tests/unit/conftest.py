# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configure unit tests for the `slurmrestd` charmed operator."""

import pytest
from charm import SlurmrestdCharm
from ops import testing
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture


def patch_slurmrestd_active(
    manager: testing.Manager[SlurmrestdCharm], mocker: MockerFixture
) -> None:
    """Patch the `slurmrestd` manager so the unit reports installed and active.

    This is the state the charm must be in before `check_slurmrestd` reports `ActiveStatus`.
    """
    mocker.patch.object(manager.charm.slurmrestd, "is_installed", return_value=True)
    mocker.patch.object(manager.charm.slurmrestd.service, "is_active", return_value=True)


@pytest.fixture(scope="function")
def mock_ctx() -> testing.Context[SlurmrestdCharm]:
    """Mock `SlurmrestdCharm` context."""
    return testing.Context(SlurmrestdCharm)


@pytest.fixture(scope="function")
def mock_charm(
    mock_ctx, fs: FakeFilesystem, mocker: MockerFixture
) -> testing.Context[SlurmrestdCharm]:
    """Mock `SlurmrestdCharm` context with fake filesystem.

    Warnings:
        - The mock charm context must come before the fake filesystem fixture,
          otherwise `ops.testing.Context` will fail to locate the `slurmrestd` charm's
          charmcraft.yaml file.
    """
    fs.create_file("/etc/slurm/slurm.jwks", create_missing_dirs=True)
    fs.create_file("/etc/default/slurmrestd", create_missing_dirs=True)
    mocker.patch("shutil.chown")  # User/group `slurm` doesn't exist on host.
    mocker.patch("subprocess.run")

    return mock_ctx


@pytest.fixture(scope="function", params=(True, False), ids=("success", "failure"))
def succeed(request: pytest.FixtureRequest) -> bool:
    """Parameterize a test to succeed and fail."""
    return request.param
