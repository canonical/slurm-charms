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

"""BDD step definitions for slurmctld high availability."""

import json
import logging
import subprocess

import jubilant
import pytest
from constants import (
    CEPHFS_SERVER_PROXY_APP_NAME,
    MICROCEPH_APP_NAME,
    SACKD_APP_NAME,
    SLURM_APPS,
    SLURM_WAIT_TIMEOUT,
    SLURMCTLD_APP_NAME,
)
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_jubilant_bdd import Context
from utils import node_name, scontrol_show_node

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.order(19),
    pytest.mark.high_availability,
]

scenarios("features/slurmctld_high_availability.feature")


# ---------------------------------------------------------------------------
# Slurm controller discovery via ``scontrol ping``
# ---------------------------------------------------------------------------


def _get_slurm_controllers(context: Context, query_unit: str = f"{SACKD_APP_NAME}/0") -> dict:
    """Return a dict of Slurmctld controller statuses keyed by mode.

    Polls ``scontrol ping --json`` on the login node and correlates ping
    results with ``juju status`` to map modes (primary, backup, ...) to
    unit, leader, and machine metadata.
    """
    juju = context.get_juju()
    status = juju.status()
    ping_output = json.loads(juju.exec("scontrol ping --json", unit=query_unit).stdout)
    pings = ping_output["pings"]
    pings_by_hostname = {ping["hostname"]: ping for ping in pings}

    slurm_controllers = {}
    for unit, unit_status in status.apps[SLURMCTLD_APP_NAME].units.items():
        hostname = status.machines[unit_status.machine].instance_id
        if hostname in pings_by_hostname:
            ping_data = pings_by_hostname[hostname]
            ping_data["unit"] = unit
            ping_data["leader"] = unit_status.leader
            ping_data["machine"] = unit_status.machine
            slurm_controllers[ping_data["mode"]] = ping_data

    return slurm_controllers


def _wait_for_controllers(context: Context, predicate) -> dict:
    """Poll ``_get_slurm_controllers`` until ``predicate(controllers)`` passes."""

    def ready(_ctx: Context) -> bool:
        try:
            controllers = _get_slurm_controllers(context)
            predicate(controllers)
            return True
        except Exception:
            return False

    context.wait(ready=ready)
    return _get_slurm_controllers(context)


def _controllers(context: Context) -> dict:
    """Return recorded controller snapshot if available, else query fresh.

    Steps that need stable unit/machine references across failover or
    recovery must use this helper so the mode-to-unit mapping captured
    *before* the state change is used throughout the scenario.
    """
    scenario_state = context.scenario_state
    if "ha_controllers" in scenario_state:
        return scenario_state["ha_controllers"]
    return _get_slurm_controllers(context)


# ---------------------------------------------------------------------------
# Juju machine status helpers
# ---------------------------------------------------------------------------


def _down_controller_machines(context: Context) -> dict[str, str]:
    """Return a mapping of slurmctld units to machine ids whose juju machine is down."""
    juju = context.get_juju()
    status = juju.status()
    return {
        unit: unit_status.machine
        for unit, unit_status in status.apps[SLURMCTLD_APP_NAME].units.items()
        if status.machines[unit_status.machine].juju_status.current == "down"
    }


def _machine_is_down(status: jubilant.Status, machine_id: str) -> bool:
    """Return ``True`` if the juju machine's agent status is ``down``."""
    return status.machines[machine_id].juju_status.current == "down"


# ---------------------------------------------------------------------------
# Deploy steps with constraints / storage / config
# ---------------------------------------------------------------------------


@given(
    parsers.parse(
        "I deploy 'cephfs-server-proxy' from channel '{channel}' "
        "with cephfs config gathered from unit 'microceph/0'"
    )
)
def deploy_cephfs_proxy(context: Context, channel: str) -> None:
    """Gather CephFS config from microceph and deploy cephfs-server-proxy."""
    juju = context.get_juju()
    microceph_unit = f"{MICROCEPH_APP_NAME}/0"

    microceph_host = juju.exec("hostname -I", unit=microceph_unit).stdout.strip()
    microceph_fsid = juju.exec(
        "source /etc/profile.d/apps-bin-path.sh && microceph.ceph -s -f json | jq -r '.fsid'",
        unit=microceph_unit,
    ).stdout.strip()
    microceph_key = juju.exec(
        "source /etc/profile.d/apps-bin-path.sh && microceph.ceph auth print-key client.fs-client",
        unit=microceph_unit,
    ).stdout

    juju.deploy(
        CEPHFS_SERVER_PROXY_APP_NAME,
        CEPHFS_SERVER_PROXY_APP_NAME,
        channel=channel,
        config={
            "fsid": microceph_fsid,
            "sharepoint": "cephfs:/",
            "monitor-hosts": microceph_host,
            "auth-info": f"fs-client:{microceph_key}",
        },
    )


# ---------------------------------------------------------------------------
# CephFS setup
# ---------------------------------------------------------------------------


@given(parsers.parse("I set up the cephfs pools and client on unit '{unit}'"))
def setup_cephfs(context: Context, unit: str) -> None:
    """Create CephFS pools and authorise a client on microceph."""
    juju = context.get_juju()
    juju.exec(
        "source /etc/profile.d/apps-bin-path.sh && "
        "microceph.ceph osd pool create cephfs_data && "
        "microceph.ceph osd pool create cephfs_metadata && "
        "microceph.ceph fs new cephfs cephfs_metadata cephfs_data && "
        "microceph.ceph fs authorize cephfs client.fs-client / rw",
        unit=unit,
    )


# ---------------------------------------------------------------------------
# Controller snapshot and hostname continuity
# ---------------------------------------------------------------------------


@given("I record the current slurmctld controller mode assignments")
def record_controllers(context: Context) -> None:
    """Snapshot the current slurm controller modes for stable unit references.

    Subsequent When/Then steps reference units by their recorded mode
    (primary/backup/...) rather than re-querying ``scontrol ping``, whose
    mode assignments may shift after failover.
    """
    context.scenario_state["ha_controllers"] = _get_slurm_controllers(context)


@given(parsers.parse("there are '{down}' down and '{up}' up slurmctld controller machines"))
def controller_unit_count(context: Context, down: str, up: str) -> None:
    """Assert the number of down and up slurmctld units by machine status."""
    juju = context.get_juju()
    down_count = len(_down_controller_machines(context))
    up_count = len(juju.status().apps[SLURMCTLD_APP_NAME].units) - down_count
    assert down_count == int(down), f"expected {down} down units, got {down_count}"
    assert up_count == int(up), f"expected {up} up units, got {up_count}"


@then(
    parsers.parse(
        "the slurmctld controller that is {mode} has the hostname recorded for {recorded_mode}"
    )
)
def controller_hostname_unchanged(context: Context, mode: str, recorded_mode: str) -> None:
    """Assert the current controller's hostname matches the recorded snapshot."""
    recorded = context.scenario_state["ha_controllers"]

    def check(controllers):
        assert mode in controllers, f"controller mode '{mode}' not found"
        assert recorded_mode in recorded, f"recorded mode '{recorded_mode}' not found"
        actual = controllers[mode]["hostname"]
        expected = recorded[recorded_mode]["hostname"]
        assert actual == expected, (
            f"hostname mismatch for {mode} vs recorded {recorded_mode}: "
            f"expected '{expected}', got '{actual}'"
        )

    _wait_for_controllers(context, check)


# ---------------------------------------------------------------------------
# Controller status assertions
# ---------------------------------------------------------------------------


@given(parsers.parse("the slurmctld controller that is {mode} reports ping status '{status}'"))
@then(parsers.parse("the slurmctld controller that is {mode} reports ping status '{status}'"))
def controller_status(context: Context, mode: str, status: str) -> None:
    """Assert that the controller in the given mode has the given pinged status."""

    def check(controllers):
        assert mode in controllers, f"controller mode '{mode}' not found"
        assert controllers[mode]["pinged"] == status, (
            f"expected {mode} to be '{status}', got '{controllers[mode]['pinged']}'"
        )

    _wait_for_controllers(context, check)


@given(parsers.parse("there are '{count}' slurmctld controllers registered"))
@then(parsers.parse("there are '{count}' slurmctld controllers registered"))
def controller_count(context: Context, count: str) -> None:
    """Assert the number of registered slurm controllers."""

    def check(controllers):
        assert len(controllers) == int(count), (
            f"expected {count} controllers, got {len(controllers)}"
        )

    _wait_for_controllers(context, check)


# ---------------------------------------------------------------------------
# Scale up / down
# ---------------------------------------------------------------------------


@when(parsers.parse("I remove the slurmctld controller that is {mode}"))
def remove_controller_unit(context: Context, mode: str) -> None:
    """Remove the slurmctld unit corresponding to the given controller mode.

    ``mode`` is normally a slurmctld ping mode (primary, backup, backup1,
    ...). The literal value ``down`` is handled specially: the unit whose
    backing machine is powered off (juju status ``down``) is removed with
    ``force=True`` rather than being looked up via ``scontrol ping``.
    """
    juju = context.get_juju()
    if mode == "down":
        down_units = _down_controller_machines(context)
        assert down_units, "no down controller unit found"
        down_unit = next(iter(down_units))
        juju.remove_unit(down_unit, force=True)
        juju.wait(
            lambda status: jubilant.all_active(status, *SLURM_APPS),
            timeout=SLURM_WAIT_TIMEOUT,
        )
        return

    controllers = _get_slurm_controllers(context)
    assert mode in controllers, f"controller mode '{mode}' not found"
    removed_unit = controllers[mode]["unit"]
    expected_units = len(juju.status().apps[SLURMCTLD_APP_NAME].units) - 1
    juju.remove_unit(removed_unit)
    juju.wait(
        lambda status: (
            removed_unit not in status.apps[SLURMCTLD_APP_NAME].units
            and len(status.apps[SLURMCTLD_APP_NAME].units) == expected_units
            and jubilant.all_active(status, *SLURM_APPS)
        ),
        error=lambda status: jubilant.any_error(status, SLURMCTLD_APP_NAME),
        timeout=SLURM_WAIT_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Service failover / recovery
# ---------------------------------------------------------------------------


@when(
    parsers.re(
        r"I (?P<operation>stop|restart) the slurmctld service on the controller that is (?P<mode>\w+)"
    )
)
def control_slurmctld_service(context: Context, operation: str, mode: str) -> None:
    """Stop or restart the slurmctld service on the given controller mode's unit."""
    juju = context.get_juju()
    controllers = _controllers(context)
    slurmctld_service = SLURM_APPS[SLURMCTLD_APP_NAME]
    juju.exec(
        f"sudo systemctl {operation} {slurmctld_service}",
        unit=controllers[mode]["unit"],
    )


@then(parsers.parse("the slurm sinfo command succeeds on unit '{unit}'"))
def sinfo_succeeds(context: Context, unit: str) -> None:
    """Poll until ``sinfo`` returns successfully on the given unit."""
    juju = context.get_juju()

    def ready(_ctx: Context) -> bool:
        try:
            result = juju.exec("sinfo", unit=unit, wait=30)
            return result.return_code == 0
        except Exception:
            return False

    context.wait(ready=ready)


_SERVICE_STATES = {
    "running as primary": "Running as primary controller",
    "running in background mode": "slurmctld running in background mode",
}


@then(
    parsers.re(
        r"the slurmctld service on the controller that is (?P<mode>\w+) "
        r"is (?P<state>running as primary|running in background mode)"
    )
)
def controller_service_state(context: Context, mode: str, state: str) -> None:
    """Assert the service on the given controller mode reports the given state.

    Polls ``systemctl status`` until the expected state substring appears,
    e.g. "Running as primary controller" after a failover, or "slurmctld
    running in background mode" once a backup demotes itself.
    """
    juju = context.get_juju()
    controllers = _controllers(context)
    slurmctld_service = SLURM_APPS[SLURMCTLD_APP_NAME]
    unit = controllers[mode]["unit"]
    expected = _SERVICE_STATES[state]

    def ready(_ctx: Context) -> bool:
        try:
            result = juju.exec(
                f"systemctl status {slurmctld_service}",
                unit=unit,
            )
            logger.debug(
                "service status on '%s':\nreturn_code=%s\nstdout=%s\nstderr=%s",
                unit,
                result.return_code,
                result.stdout,
                result.stderr,
            )
            return expected in result.stdout
        except Exception as exc:
            logger.debug("service status check on '%s' raised: %s", unit, exc)
            return False

    context.wait(ready=ready)


# ---------------------------------------------------------------------------
# Compute node scheduling precondition
# ---------------------------------------------------------------------------


@given(
    parsers.parse(
        "the slurmd node for unit '{compute_unit}' is schedulable according to scontrol from unit '{login_unit}'"
    )
)
def node_is_schedulable(context: Context, compute_unit: str, login_unit: str) -> None:
    """Ensure the compute node is schedulable before testing failover.

    Queries ``scontrol show node`` from the login unit. If the node is not
    in a schedulable state (e.g. ``DOWN``), runs the ``set-node-state``
    action on the recorded primary controller to set it to ``idle``, then
    polls until the node is schedulable.

    This makes the HA feature self-contained: it does not rely on the
    node-operations feature having already put the node into ``IDLE``.
    """
    juju = context.get_juju()
    name = node_name(compute_unit)
    controllers = _controllers(context)
    action_unit = controllers["primary"]["unit"]

    non_schedulable = {"DOWN", "DRAIN", "FAIL", "FAILING", "RESERVED", "UNKNOWN"}

    def _node_state() -> tuple[list[str], str]:
        """Return (states, reason) for the compute node, querying from login."""
        data = scontrol_show_node(context, login_unit, name)
        nodes = data.get("nodes", [])
        if not nodes:
            return [], "node not found"
        states = nodes[0].get("state", [])
        if isinstance(states, str):
            states = [states]
        reason = nodes[0].get("reason", "")
        return states, reason

    def _is_schedulable(states: list[str]) -> bool:
        return bool(states) and not any(s in non_schedulable for s in states)

    states, reason = _node_state()
    logger.debug(
        "node_is_schedulable: node '%s' initial state=%s, reason=%s",
        name,
        states,
        reason,
    )

    if not _is_schedulable(states):
        logger.info(
            "node_is_schedulable: node '%s' is not schedulable (state=%s). "
            "Running set-node-state action on unit '%s' to set state=idle.",
            name,
            states,
            action_unit,
        )
        juju.run(action_unit, "set-node-state", params={"nodes": name, "state": "idle"})

    def ready(_ctx: Context) -> bool:
        try:
            states, reason = _node_state()
            logger.debug(
                "node_is_schedulable: polling node '%s' state=%s, reason=%s",
                name,
                states,
                reason,
            )
            return _is_schedulable(states)
        except Exception as exc:
            logger.debug("node_is_schedulable: polling node '%s' raised: %s", name, exc)
            return False

    context.wait(ready=ready)


# ---------------------------------------------------------------------------
# Machine power off / reboot
# ---------------------------------------------------------------------------


@when("I power off the primary slurmctld machine")
def power_off_primary(context: Context) -> None:
    """Power off the primary controller's machine."""
    juju = context.get_juju()
    controllers = _controllers(context)
    juju.exec("sudo poweroff", unit=controllers["primary"]["unit"])
    machine_id = controllers["primary"]["machine"]
    juju.wait(
        lambda status: _machine_is_down(status, machine_id),
        timeout=SLURM_WAIT_TIMEOUT,
    )


@given("the primary slurmctld machine is powered off")
@then("the primary slurmctld machine is powered off")
def primary_machine_off(context: Context) -> None:
    """Assert the primary controller's machine juju status is 'down'."""
    juju = context.get_juju()
    controllers = _controllers(context)
    machine_id = controllers["primary"]["machine"]

    def ready(_ctx: Context) -> bool:
        return _machine_is_down(juju.status(), machine_id)

    context.wait(ready=ready)


@when("I reboot the primary slurmctld machine")
def reboot_primary_machine(context: Context) -> None:
    """Start the powered-off primary machine via lxc."""
    controllers = _controllers(context)
    hostname = controllers["primary"]["hostname"]
    subprocess.check_output(["lxc", "start", hostname])
