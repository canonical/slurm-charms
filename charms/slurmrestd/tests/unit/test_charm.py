#!/usr/bin/env python3
# Copyright 2023-2025 Canonical Ltd.
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

"""Unit tests for the `slurmrestd` charm."""

import json
from pathlib import Path

import ops
import pytest
from charmed_hpc_libs.errors import SystemdError
from charmed_hpc_libs.ops.machine.apt import AptOpsManager
from charmed_hpc_libs.ops.machine.systemd import SystemctlServiceManager
from charmed_slurm_slurmctld_interface import AUTH_KEY_LABEL
from conftest import patch_slurmrestd_active
from constants import SLURMRESTD_INTEGRATION_NAME, SLURMRESTD_PORT
from ops import testing
from pytest_mock import MockerFixture
from slurm_ops import SlurmOpsError
from slurmutils import SlurmConfig

EXAMPLE_AUTH_KEY = "xyz123=="
EXAMPLE_AUTH_KEY_ID = "12345678-90ab-cdef-1234-567890abcdef"
EXAMPLE_CONTROLLERS = ["juju-988225-0:6817", "juju-988225-1:6817"]
EXAMPLE_SLURM_CONFIG = {
    "slurm.conf": SlurmConfig(
        clustername="charmed-hpc",
        slurmctldhost=EXAMPLE_CONTROLLERS,
    ),
    "slurm.conf.accounting": SlurmConfig(
        accountingstoragetype="accounting_storage/slurmdbd",
        accountingstoragehost="juju-988225-0",
    ),
}
ROTATED_AUTH_KEY = "abc789=="
ROTATED_AUTH_KEY_ID = "fedcba09-8765-4321-fedc-ba0987654321"
EXAMPLE_KEY_FILE_CONTENT = {
    "keys": [{"alg": "HS256", "kty": "oct", "kid": EXAMPLE_AUTH_KEY_ID, "k": EXAMPLE_AUTH_KEY}]
}
ROTATED_KEY_FILE_CONTENT = {
    "keys": [{"alg": "HS256", "kty": "oct", "kid": ROTATED_AUTH_KEY_ID, "k": ROTATED_AUTH_KEY}]
}


@pytest.fixture
def auth_key_secret() -> testing.Secret:
    """Mock Slurm auth key secret."""
    return testing.Secret(
        label=AUTH_KEY_LABEL,
        tracked_content={"key": EXAMPLE_AUTH_KEY, "keyid": EXAMPLE_AUTH_KEY_ID},
    )


def slurmctld_integration(
    auth_key_secret: testing.Secret, *, ready: bool = True
) -> testing.Relation:
    """Build the `slurmctld` integration as the `slurmctld` application publishes it.

    Args:
        auth_key_secret: Secret holding the Slurm auth key shared over the integration.
        ready: Whether the remote application databag contains all data required by
            `SlurmrestdProvider` (i.e. `auth_secret_id` and `slurmconfig`).
    """
    return testing.Relation(
        endpoint=SLURMRESTD_INTEGRATION_NAME,
        interface="slurmrestd",
        id=1,
        remote_app_name="slurmctld",
        remote_app_data=(
            {
                "auth_secret_id": json.dumps(auth_key_secret.id),
                "slurmconfig": json.dumps(
                    {name: config.dict() for name, config in EXAMPLE_SLURM_CONFIG.items()}
                ),
            }
            if ready
            else {"auth_secret_id": json.dumps("")}
        ),
    )


@pytest.mark.parametrize(
    "leader",
    (
        pytest.param(True, id="leader"),
        pytest.param(False, id="not leader"),
    ),
)
class TestSlurmrestdCharm:
    """Unit tests for the `slurmrestd` charmed operator."""

    @pytest.mark.parametrize(
        "mock_install,install_success",
        (
            pytest.param(None, True, id="success"),
            pytest.param(SlurmOpsError("install failed"), False, id="fail"),
        ),
    )
    def test_on_install(
        self,
        mock_charm,
        mocker: MockerFixture,
        mock_install,
        install_success,
        leader,
    ) -> None:
        """Test the `_on_install` event handler.

        Failure mode: `apt` enables `slurmrestd` on install. If the charm fails to
        stop and disable the service, it starts serving the REST API before any
        configuration or auth key exists. If an install failure is not deferred, the
        unit never retries once `apt` recovers.
        """
        with mock_charm(mock_charm.on.install(), testing.State(leader=leader)) as manager:
            slurmrestd = manager.charm.slurmrestd
            mocker.patch.object(slurmrestd, "install", side_effect=mock_install)
            mocker.patch.object(slurmrestd, "is_installed", return_value=install_success)
            mocker.patch.object(slurmrestd, "version", return_value="24.05.2-1")
            mock_stop = mocker.patch.object(slurmrestd.service, "stop")
            mock_disable = mocker.patch.object(slurmrestd.service, "disable")

            state = manager.run()

        if install_success:
            assert state.workload_version == "24.05.2-1"
            assert state.opened_ports == frozenset(
                {testing.TCPPort(port=SLURMRESTD_PORT, protocol="tcp")}
            )
            mock_stop.assert_called_once()
            mock_disable.assert_called_once()
            assert state.unit_status == ops.BlockedStatus(
                "Waiting for integrations: [`slurmctld`]"
            )
        else:
            assert len(state.deferred) > 0
            assert state.opened_ports == frozenset()
            assert state.unit_status == ops.BlockedStatus(
                "Failed to install `slurmrestd`. See `juju debug-log` for details."
            )

    @pytest.mark.parametrize(
        "ready",
        (
            pytest.param(True, id="ready"),
            pytest.param(False, id="not ready"),
        ),
    )
    def test_on_slurmctld_ready(
        self, mock_charm, mocker: MockerFixture, leader, ready, auth_key_secret
    ) -> None:
        """Test the `_on_slurmctld_ready` event handler.

        Failure mode: `slurmrestd` authenticates REST API clients with the auth key
        and `slurm.conf` contents published by `slurmctld`. If the key or config
        files are not written before the service is (re)started, the API rejects
        every request.
        """
        integration = slurmctld_integration(auth_key_secret, ready=ready)

        with mock_charm(
            mock_charm.on.relation_changed(integration),
            testing.State(leader=leader, relations={integration}, secrets={auth_key_secret}),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            patch_slurmrestd_active(manager, mocker)
            mock_enable = mocker.patch.object(slurmrestd.service, "enable")
            mock_restart = mocker.patch.object(slurmrestd.service, "restart")

            state = manager.run()

        if ready:
            key_file_content = json.loads(Path("/etc/slurm/slurm.jwks").read_text())
            assert key_file_content == EXAMPLE_KEY_FILE_CONTENT

            slurm_conf = Path("/etc/slurm/slurm.conf").read_text()
            assert "clustername=charmed-hpc" in slurm_conf
            assert "slurmctldhost=juju-988225-0:6817" in slurm_conf
            assert "slurmctldhost=juju-988225-1:6817" in slurm_conf

            accounting_conf = Path("/etc/slurm/slurm.conf.accounting").read_text()
            assert "accountingstoragetype=accounting_storage/slurmdbd" in accounting_conf

            mock_enable.assert_called_once()
            mock_restart.assert_called_once()
            assert len(state.deferred) == 0
            assert state.unit_status == ops.ActiveStatus()
        else:
            # The `@wait_unless(controller_ready)` guard defers until `slurmctld`
            # publishes all required integration data.
            assert len(state.deferred) == 1
            assert state.unit_status == ops.WaitingStatus("Waiting for controller data")

    def test_on_slurmctld_ready_converges_repeated_events(
        self, mock_charm, mocker: MockerFixture, leader, auth_key_secret
    ) -> None:
        """Test that repeated `_on_slurmctld_ready` events converge to a singular state.

        Failure mode: `relation-changed` fires many times in production. If the
        handler appended to the auth key file or config files instead of replacing
        their contents, duplicate keys and config lines would accumulate and break
        `slurmrestd` over time.
        """
        integration = slurmctld_integration(auth_key_secret)
        input_state = testing.State(
            leader=leader, relations={integration}, secrets={auth_key_secret}
        )

        # Patch on the classes rather than on charm instances so the patches apply
        # to both runs (each run constructs a new charm and service manager).
        mocker.patch.object(AptOpsManager, "is_installed", return_value=True)
        mocker.patch.object(SystemctlServiceManager, "is_active", return_value=True)
        mocker.patch.object(SystemctlServiceManager, "enable")
        mock_restart = mocker.patch.object(SystemctlServiceManager, "restart")

        # Run the same event twice through the harness.
        with mock_charm(mock_charm.on.relation_changed(integration), input_state) as manager:
            manager.run()
        with mock_charm(mock_charm.on.relation_changed(integration), input_state) as manager:
            manager.run()

        key_file_content = json.loads(Path("/etc/slurm/slurm.jwks").read_text())
        assert key_file_content == EXAMPLE_KEY_FILE_CONTENT

        slurm_conf = Path("/etc/slurm/slurm.conf").read_text()
        clustername_lines = [ln for ln in slurm_conf.splitlines() if ln.startswith("clustername=")]
        assert clustername_lines == ["clustername=charmed-hpc"]

        assert mock_restart.call_count == 2

    def test_on_slurmctld_ready_restart_failure(
        self, mock_charm, mocker: MockerFixture, leader, auth_key_secret
    ) -> None:
        """Test `_on_slurmctld_ready` when restarting the `slurmrestd` service fails.

        Failure mode: `service.restart()` raises `SystemdError`, which is a sibling of
        `SlurmOpsError` rather than a subclass. If the handler stops catching it, the
        exception escapes, the unit lands in Juju `error` status instead of blocked,
        and the event is lost rather than deferred for retry.
        """
        integration = slurmctld_integration(auth_key_secret)

        with mock_charm(
            mock_charm.on.relation_changed(integration),
            testing.State(leader=leader, relations={integration}, secrets={auth_key_secret}),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            patch_slurmrestd_active(manager, mocker)
            mocker.patch.object(slurmrestd.service, "enable")
            mocker.patch.object(
                slurmrestd.service, "restart", side_effect=SystemdError("restart failed")
            )

            state = manager.run()

        assert len(state.deferred) == 1
        assert state.unit_status == ops.BlockedStatus(
            "Failed to start `slurmrestd`. See `juju debug-log` for details"
        )

    def test_on_slurmctld_disconnected(
        self, mock_charm, mocker: MockerFixture, leader, auth_key_secret
    ) -> None:
        """Test the `_on_slurmctld_disconnected` event handler.

        Failure mode: when the `slurmctld` integration is removed, a still-running
        `slurmrestd` keeps serving an API backed by a controller that no longer
        recognizes its auth key. The service must be disabled and stopped.
        """
        integration = slurmctld_integration(auth_key_secret)

        with mock_charm(
            mock_charm.on.relation_broken(integration),
            testing.State(leader=leader, relations={integration}, secrets={auth_key_secret}),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            mocker.patch.object(slurmrestd, "is_installed", return_value=True)
            mock_disable = mocker.patch.object(slurmrestd.service, "disable")
            mock_stop = mocker.patch.object(slurmrestd.service, "stop")

            state = manager.run()

        mock_disable.assert_called_once()
        mock_stop.assert_called_once()
        assert len(state.deferred) == 0
        assert state.unit_status == ops.BlockedStatus("Waiting for integrations: [`slurmctld`]")

    def test_on_slurmctld_disconnected_stop_failure(
        self, mock_charm, mocker: MockerFixture, leader, auth_key_secret
    ) -> None:
        """Test `_on_slurmctld_disconnected` when stopping the `slurmrestd` service fails.

        Failure mode: `service.stop()` raises `SystemdError`, which is a sibling of
        `SlurmOpsError` rather than a subclass. If the handler stops catching it, the
        exception escapes, the unit lands in Juju `error` status instead of blocked,
        and the event is lost rather than deferred for retry.
        """
        integration = slurmctld_integration(auth_key_secret)

        with mock_charm(
            mock_charm.on.relation_broken(integration),
            testing.State(leader=leader, relations={integration}, secrets={auth_key_secret}),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            mocker.patch.object(slurmrestd, "is_installed", return_value=True)
            mocker.patch.object(slurmrestd.service, "disable")
            mocker.patch.object(
                slurmrestd.service, "stop", side_effect=SystemdError("stop failed")
            )

            state = manager.run()

        assert len(state.deferred) == 1
        assert state.unit_status == ops.BlockedStatus(
            "Failed to stop `slurmrestd`. See `juju debug-log` for details"
        )

    def test_on_secret_changed_success(self, mock_charm, mocker: MockerFixture, leader) -> None:
        """Test successful execution of the `_on_secret_changed` event handler.

        Failure mode: when `slurmctld` rotates the auth key it adds a new secret
        revision, so the handler must read the *latest* revision
        (`get_content(refresh=True)`). Reading the stale tracked revision would
        leave `slurmrestd` authenticating with the old key while the rest of the
        cluster has moved on, rejecting every REST API request.

        The key file must also be *replaced*, not appended to (`key.set`, not
        `key.apply`), and the service restarted rather than reloaded: unlike other
        Slurm services, `slurmrestd` shuts down when sent the reload signal.
        """
        key_file_path = Path("/etc/slurm/slurm.jwks")
        # A rotated secret: the charm still tracks the old revision, and the new
        # key is only visible on the latest revision.
        rotated_secret = testing.Secret(
            label=AUTH_KEY_LABEL,
            tracked_content={"key": EXAMPLE_AUTH_KEY, "keyid": EXAMPLE_AUTH_KEY_ID},
            latest_content={"key": ROTATED_AUTH_KEY, "keyid": ROTATED_AUTH_KEY_ID},
        )
        # Pre-existing key file holding the pre-rotation key, as it would be on disk.
        key_file_path.write_text(json.dumps(EXAMPLE_KEY_FILE_CONTENT))
        integration = slurmctld_integration(rotated_secret)

        with mock_charm(
            mock_charm.on.secret_changed(rotated_secret),
            testing.State(leader=leader, relations={integration}, secrets={rotated_secret}),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            patch_slurmrestd_active(manager, mocker)
            mock_restart = mocker.patch.object(slurmrestd.service, "restart")
            mock_reload = mocker.patch.object(slurmrestd.service, "reload")

            state = manager.run()

        # Only the rotated key is present: the new revision was read, and the old
        # entry was replaced rather than appended to.
        assert json.loads(key_file_path.read_text()) == ROTATED_KEY_FILE_CONTENT
        mock_restart.assert_called_once()
        mock_reload.assert_not_called()
        assert state.unit_status == ops.ActiveStatus()

    def test_on_secret_changed_empty_key_id_failure(
        self, mock_charm, mocker: MockerFixture, leader
    ) -> None:
        """Test `_on_secret_changed` event handler when auth key ID is empty.

        Failure mode: an empty key ID means the rotated secret is unusable. The
        handler must block and defer rather than write a malformed key file that
        would break authentication for every REST API client.
        """
        auth_key_secret = testing.Secret(
            label=AUTH_KEY_LABEL, tracked_content={"key": EXAMPLE_AUTH_KEY, "keyid": ""}
        )
        integration = slurmctld_integration(auth_key_secret)

        with mock_charm(
            mock_charm.on.secret_changed(auth_key_secret),
            testing.State(leader=leader, relations={integration}, secrets={auth_key_secret}),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            mocker.patch.object(slurmrestd, "is_installed", return_value=True)

            state = manager.run()

        assert len(state.deferred) == 1
        assert state.unit_status == ops.BlockedStatus(
            "Failed to retrieve Slurm authentication key. See `juju debug-log` for details"
        )

    def test_on_secret_changed_ignores_unrelated_secret(
        self, mock_charm, mocker: MockerFixture, leader, auth_key_secret
    ) -> None:
        """Test that `_on_secret_changed` ignores secrets that are not the auth key.

        Failure mode: if the label guard were removed, any other secret observed
        by this unit would overwrite `/etc/slurm/slurm.jwks` with foreign content
        and needlessly restart the service, breaking authentication for every
        REST API client.
        """
        key_file_path = Path("/etc/slurm/slurm.jwks")
        sentinel_content = {
            "keys": [{"alg": "HS256", "kty": "oct", "kid": "sentinel", "k": "c2VudGluZWw="}]
        }
        key_file_path.write_text(json.dumps(sentinel_content))

        unrelated_secret = testing.Secret(
            label="user-data", tracked_content={"key": "not-the-auth-key=="}
        )
        integration = slurmctld_integration(auth_key_secret)

        with mock_charm(
            mock_charm.on.secret_changed(unrelated_secret),
            testing.State(
                leader=leader,
                relations={integration},
                secrets={auth_key_secret, unrelated_secret},
            ),
        ) as manager:
            slurmrestd = manager.charm.slurmrestd
            patch_slurmrestd_active(manager, mocker)
            mock_restart = mocker.patch.object(slurmrestd.service, "restart")

            state = manager.run()

        assert json.loads(key_file_path.read_text()) == sentinel_content
        mock_restart.assert_not_called()
        assert state.unit_status == ops.ActiveStatus()

    @pytest.mark.parametrize(
        "installed,joined,active,expected",
        (
            pytest.param(
                False,
                False,
                False,
                ops.BlockedStatus(
                    "`slurmrestd` is not installed. See `juju debug-log` for details"
                ),
                id="not installed",
            ),
            pytest.param(
                True,
                False,
                False,
                ops.BlockedStatus("Waiting for integrations: [`slurmctld`]"),
                id="waiting for integrations",
            ),
            pytest.param(
                True,
                True,
                False,
                ops.WaitingStatus("Waiting for `slurmrestd` to start"),
                id="waiting for service",
            ),
            pytest.param(True, True, True, ops.ActiveStatus(), id="active"),
        ),
    )
    def test_update_status(
        self,
        mock_charm,
        mocker: MockerFixture,
        installed,
        joined,
        active,
        expected,
        leader,
    ) -> None:
        """Test the status surface evaluated by `check_slurmrestd` after every handler.

        Failure mode: these statuses are what operators diagnose outages from. A
        wrong branch here misleads operators, e.g. showing "waiting" while the
        service is actually broken.
        """
        integration = (
            testing.Relation(
                endpoint=SLURMRESTD_INTEGRATION_NAME,
                interface="slurmrestd",
                remote_app_name="slurmctld",
            )
            if joined
            else None
        )
        input_state = testing.State(
            leader=leader, relations={integration} if integration else set()
        )

        with mock_charm(mock_charm.on.update_status(), input_state) as manager:
            slurmrestd = manager.charm.slurmrestd
            mocker.patch.object(slurmrestd, "is_installed", return_value=installed)
            mocker.patch.object(slurmrestd.service, "is_active", return_value=active)

            state = manager.run()

        assert state.unit_status == expected
