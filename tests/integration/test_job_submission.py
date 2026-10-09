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

"""BDD step definitions for Slurm job submission."""

import logging
import textwrap
import uuid
from collections.abc import Callable, Iterator

import pytest
from constants import SACKD_APP_NAME, SLURMCTLD_APP_NAME, SLURMD_APP_NAME
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_jubilant_bdd import Context
from utils import node_name

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.order(12)

scenarios("features/slurm_job_submission.feature")


# ---------------------------------------------------------------------------
# GPU job submission with mock GPU
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_gpu_cleanup() -> Iterator[list[Callable[[], None]]]:
    """Registry of teardown callables run after the scenario, in reverse order.

    Keeps the GPU scenario a clean Given/When/Then flow: the Given step that
    sets up the mock GPU registers its cleanup here instead of the plan
    spelling out teardown steps after the Then.
    """
    cleanups: list[Callable[[], None]] = []
    try:
        yield cleanups
    finally:
        for cleanup in reversed(cleanups):
            cleanup()


@given(parsers.parse("I set up a mock NVIDIA GPU device on unit '{unit}'"))
def setup_mock_gpu(
    context: Context, mock_gpu_cleanup: list[Callable[[], None]], unit: str
) -> None:
    """Mock GPU device files on the slurmd unit for NVIDIA auto-detection.

    Registers the full teardown (mounts, mock files, node config reset,
    cgroup config reset, and node re-registration) with the
    ``mock_gpu_cleanup`` fixture so it runs even if the scenario fails.
    """
    juju = context.get_juju()

    juju.exec("mkdir -p /tmp/sys/bus/pci/drivers/nvidia/0000:01:00.0/", unit=unit)
    juju.exec(
        "cp /sys/devices/system/node/node0/cpulist "
        "/tmp/sys/bus/pci/drivers/nvidia/0000:01:00.0/local_cpulist",
        unit=unit,
    )
    juju.exec(
        "sudo mount -t overlay overlay "
        "-o lowerdir=/sys/bus/pci/drivers:/tmp/sys/bus/pci/drivers "
        "/sys/bus/pci/drivers",
        unit=unit,
    )

    gpu_information = textwrap.dedent("""\
            Model: \t\t\t Mock GPU
            IRQ: \t\t\t 185
            GPU UUID: \t\t GPU-12345678-90ab-cdef-1234-567890abcdef
            Video BIOS: \t\t 12.34.56.78.aa
            Bus Type: \t\t PCIe
            DMA Size: \t\t 47 bits
            DMA Mask: \t\t 0x7fffffffffff
            Bus Location: \t\t 0000:01:00.0
            Device Minor: \t\t 0
            GPU Firmware: \t\t 123.456.78
            GPU Excluded:\t\t No
        """)
    juju.exec("mkdir -p /tmp/proc/driver/nvidia/gpus/0000:01:00.0/", unit=unit)
    juju.exec(
        f"echo '{gpu_information}' > /tmp/proc/driver/nvidia/gpus/0000:01:00.0/information",
        unit=unit,
    )
    juju.exec("sudo mount --bind /tmp/proc/driver /proc/driver", unit=unit)

    juju.exec("sudo touch /dev/nvidia0", unit=unit)
    juju.exec("sudo mount --bind /dev/zero /dev/nvidia0", unit=unit)

    def teardown() -> None:
        """Remove the mock GPU and restore the node to its previous config."""
        cleanup_commands = [
            "sudo umount /sys/bus/pci/drivers",
            "sudo umount /proc/driver",
            "sudo umount /dev/nvidia0",
            "sudo rm -rf /tmp/sys",
            "sudo rm -rf /tmp/proc",
            "sudo rm -f /dev/nvidia0",
        ]
        for command in cleanup_commands:
            juju.exec(command, unit=unit)
        juju.run(unit, "set-node-config", params={"reset": True})
        juju.config(SLURMCTLD_APP_NAME, reset="cgroup-parameters")
        # Re-register the node last so it picks up the restored config.
        juju.exec(
            f"sudo scontrol delete nodename={node_name(unit)}",
            unit=f"{SACKD_APP_NAME}/0",
        )
        juju.exec("sudo systemctl restart slurmd", unit=unit)

    mock_gpu_cleanup.append(teardown)


@when(
    parsers.parse(
        "I re-register the slurmd node '{name}' with the slurm controller on unit '{login_unit}'"
    )
)
def reregister_slurmd_node(context: Context, name: str, login_unit: str) -> None:
    """Delete and restart the slurmd node so it re-registers with the cluster."""
    juju = context.get_juju()
    juju.exec(f"sudo scontrol delete nodename={name}", unit=login_unit)
    slurmd_unit = f"{SLURMD_APP_NAME}/0"
    juju.exec("sudo systemctl restart slurmd", unit=slurmd_unit)


@then(
    parsers.parse(
        "a slurm srun GPU job requesting 1 GPU submitted from unit '{login_unit}' runs on unit '{compute_unit}'"
    )
)
def gpu_job_submission(context: Context, login_unit: str, compute_unit: str) -> None:
    """Submit a GPU-requesting job and verify it runs on the compute node."""
    juju = context.get_juju()
    slurmd_result = juju.exec("hostname -s", unit=compute_unit)
    job_name = f"bdd-gpu-{uuid.uuid4().hex[:8]}"

    def ready(_ctx: Context) -> bool:
        try:
            sackd_result = juju.exec(
                f"srun -J {job_name} --partition {SLURMD_APP_NAME} --gres gpu:1 hostname -s",
                unit=login_unit,
            )
            assert sackd_result.success
            assert sackd_result.stdout == slurmd_result.stdout
            return True
        except Exception:
            return False

    context.wait(ready=ready)

    # Verify the job was recorded as COMPLETED in Slurm accounting.
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
