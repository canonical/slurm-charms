#!/usr/bin/env python3
# Copyright 2025-2026 Canonical Ltd.
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

"""Unit tests for the classes and functions in the `slurm_ops.core.base` module."""

import stat
import subprocess
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from charmed_hpc_libs.errors import AptError
from constants import (
    SLURM_VERSION,
    ULIMIT_CONFIG,
)
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture
from slurm_ops import (
    SackdManager,
    SlurmctldManager,
    SlurmdbdManager,
    SlurmdManager,
    SlurmOpsError,
    SlurmrestdManager,
)
from slurm_ops.core import SlurmManager

services = ["sackd", "slurmctld", "slurmd", "slurmdbd", "slurmrestd"]


class TestSlurmManager:
    """Unit tests for the :class:``SlurmManager`` class."""

    @pytest.fixture(
        params=zip(
            [SackdManager, SlurmctldManager, SlurmdManager, SlurmdbdManager, SlurmrestdManager],
            services,
        ),
        ids=services,
    )
    def mock_manager(self, request, fs: FakeFilesystem) -> tuple[SlurmManager, str]:
        """Request a mocked Slurm service manager and service name."""
        fs.create_dir("/etc/default")
        fs.create_dir("/etc/security/limits.d")
        fs.create_dir("/etc/systemd/service/slurmctld.service.d")
        fs.create_dir("/etc/systemd/service/slurmd.service.d")
        fs.create_dir("/usr/lib/systemd/system")
        fs.create_dir("/var/lib/slurm")

        manager_t = request.param[0]
        if issubclass(manager_t, SlurmdManager):
            manager = manager_t(partition_name="compute")
        else:
            manager = manager_t()

        return manager, request.param[1]

    def test_install(self, mock_manager, mock_run, mocker: MockerFixture) -> None:
        """Test the `install` method."""
        manager, service = mock_manager
        mocker.patch("slurm_ops.core.base.SlurmManager._apply_overrides")
        mocker.patch("shutil.chown")

        manager.install()

        # Verify `apt-get update` and `apt-get install` were run with the correct packages.
        update_call = mock_run.call_args_list[0][0][0]
        install_call = mock_run.call_args_list[1][0][0]
        assert update_call == ["apt-get", "update"]
        assert install_call[:3] == ["apt-get", "install", "-y"]
        assert install_call[3] == service

        # Verify the state save location was created.
        f_info = Path("/var/lib/slurm").stat()
        assert stat.filemode(f_info.st_mode) == "drwxr-xr-x"
        f_info = Path("/var/lib/slurm/checkpoint").stat()
        assert stat.filemode(f_info.st_mode) == "drwxr-xr-x"

    def test_install_additional_packages(self, mock_manager, mock_run, mocker) -> None:
        """Test that the correct additional packages are installed per service."""
        manager, service = mock_manager
        mocker.patch("slurm_ops.core.base.SlurmManager._apply_overrides")
        mocker.patch("shutil.chown")

        manager.install()
        install_call = mock_run.call_args_list[1][0][0]
        match service:
            case "sackd":
                assert install_call == ["apt-get", "install", "-y", "sackd", "slurm-client"]
            case "slurmctld":
                assert install_call == [
                    "apt-get",
                    "install",
                    "-y",
                    "slurmctld",
                    "libpmix-dev",
                ]
            case "slurmd":
                assert install_call == [
                    "apt-get",
                    "install",
                    "-y",
                    "slurmd",
                    "slurm-client",
                    "libpmix-dev",
                    "openmpi-bin",
                ]
            case "slurmdbd":
                assert install_call == ["apt-get", "install", "-y", "slurmdbd"]
            case "slurmrestd":
                assert install_call == [
                    "apt-get",
                    "install",
                    "-y",
                    "slurmrestd",
                    "slurm-wlm-basic-plugins",
                ]

    def test_install_error(self, mock_manager, mock_run) -> None:
        """Test that a `SlurmOpsError` is raised if the `apt` install fails."""
        manager, service = mock_manager
        mock_run.side_effect = [
            CompletedProcess([], returncode=0),
            subprocess.CalledProcessError(
                cmd=["apt-get", "install", "-y", service],
                returncode=1,
                output="",
                stderr="failed to install",
            ),
        ]

        with pytest.raises(SlurmOpsError) as exec_info:
            manager.install()

        assert exec_info.type == SlurmOpsError
        assert exec_info.value.message == (
            f"failed to install {service}. reason: apt-get command "
            f"'apt-get install -y {service}' failed with exit code 1. reason: failed to install"
        )

    def test_version(self, mock_manager, mock_run) -> None:
        """Test the `version` method."""
        manager, service = mock_manager

        # Test `version` when the Slurm service is installed.
        mock_run.return_value = CompletedProcess([], returncode=0, stdout=SLURM_VERSION)

        assert manager.version() == SLURM_VERSION
        assert mock_run.call_args[0][0] == [
            "dpkg-query",
            "-W",
            "-f=${source:Upstream-Version}",
            service,
        ]

        # Test `version` when the Slurm service is not installed.
        mock_run.return_value = CompletedProcess([], returncode=1)

        with pytest.raises(AptError) as exec_info:
            manager.version()

        assert exec_info.type == AptError
        assert exec_info.value.message == (
            f"unable to retrieve {service} version. ensure {service} is correctly installed"
        )

    def test_is_installed(self, mock_manager, mock_run) -> None:
        """Test the `is_installed` method."""
        manager, service = mock_manager

        # Test `is_installed` when the Slurm service is installed.
        mock_run.return_value = CompletedProcess([], returncode=0)

        assert manager.is_installed() is True
        assert mock_run.call_args[0][0] == ["dpkg-query", "-W", service]

        # Test `is_installed` when the Slurm service is not installed.
        mock_run.return_value = CompletedProcess([], returncode=1)

        assert manager.is_installed() is False

    def test_set_ulimit(self, mock_manager) -> None:
        """Test the `_set_ulimit` helper method."""
        manager, _ = mock_manager
        manager._set_ulimit()

        target = Path("/etc/security/limits.d/20-charmed-hpc-openfile.conf")
        assert ULIMIT_CONFIG == target.read_text()
        f_info = target.stat()
        assert stat.filemode(f_info.st_mode) == "-rw-r--r--"

    def test_apply_overrides(self, mock_manager, mock_run) -> None:
        """Test the `_apply_overrides` helper method."""
        manager, service = mock_manager

        manager._apply_overrides()
        match service:
            case "slurmrestd":
                groupadd = mock_run.call_args_list[0][0][0]
                adduser = mock_run.call_args_list[1][0][0]
                systemctl = mock_run.call_args_list[2][0][0]

                assert groupadd == ["groupadd", "--gid", "64031", "slurmrestd"]
                assert adduser == [
                    "adduser",
                    "--system",
                    "--group",
                    "--uid",
                    "64031",
                    "--no-create-home",
                    "--home",
                    "/nonexistent",
                    "slurmrestd",
                ]
                assert systemctl == ["systemctl", "daemon-reload"]

            case _:
                assert mock_run.call_args[0][0] == ["systemctl", "daemon-reload"]

    def test_reconfigure(self, mock_manager, mock_run, mocker: MockerFixture, fs: FakeFilesystem) -> None:
        """Test the `reconfigure` method."""
        manager, service = mock_manager

        kwargs = {"restart": True} if service == "slurmctld" else {}
        if service == "slurmdbd":
            fs.create_dir("/etc/slurm")
            mocker.patch("shutil.chown")

        manager.reconfigure(**kwargs)

        systemctl_calls = [
            call[0][0] for call in mock_run.call_args_list if call[0][0][:1] == ["systemctl"]
        ]
        assert systemctl_calls == [
            ["systemctl", "reset-failed", service],
            ["systemctl", "enable", service],
            ["systemctl", "restart", service],
        ]

    def test_reconfigure_reset_failed_error(
        self, mock_manager, mock_run, mocker: MockerFixture, fs: FakeFilesystem
    ) -> None:
        """Test that a `reset-failed` error is wrapped in `SlurmOpsError`."""
        manager, service = mock_manager

        mock_run.side_effect = subprocess.CalledProcessError(
            cmd=["systemctl", "reset-failed", service],
            returncode=1,
            output="",
            stderr="reset-failed failed",
        )

        kwargs = {"restart": True} if service == "slurmctld" else {}
        if service == "slurmdbd":
            fs.create_dir("/etc/slurm")
            fs.create_file("/etc/slurm/slurmdbd.conf")
            mocker.patch("shutil.chown")

        with pytest.raises(SlurmOpsError) as exec_info:
            manager.reconfigure(**kwargs)

        assert exec_info.value.message == (
            f"failed to reconfigure Slurm service '{service}'"
        )

    def test_reconfigure_restart_error(
        self, mock_manager, mock_run, mocker: MockerFixture, fs: FakeFilesystem
    ) -> None:
        """Test that a restart error is wrapped in `SlurmOpsError`."""
        manager, service = mock_manager

        mock_run.side_effect = [
            subprocess.CompletedProcess([], returncode=0),
            subprocess.CompletedProcess([], returncode=0),
            subprocess.CalledProcessError(
                cmd=["systemctl", "restart", service],
                returncode=1,
                output="",
                stderr="restart failed",
            ),
        ]

        kwargs = {"restart": True} if service == "slurmctld" else {}
        if service == "slurmdbd":
            fs.create_dir("/etc/slurm")
            fs.create_file("/etc/slurm/slurmdbd.conf")
            mocker.patch("shutil.chown")

        with pytest.raises(SlurmOpsError) as exec_info:
            manager.reconfigure(**kwargs)

        assert exec_info.value.message == (
            f"failed to reconfigure Slurm service '{service}'"
        )
