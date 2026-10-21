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

"""Shared helpers for the Slurm BDD step definitions."""

import json
import logging
import re
import shlex
import socket
from email import message_from_string, policy
from email.message import EmailMessage
from typing import Any

from jubilant import Task, TaskError
from psutil import net_if_addrs
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)


def scontrol_show_node(context, unit: str, name: str) -> dict[str, Any]:
    """Run ``scontrol --json show node <name>`` on ``unit`` and return parsed JSON."""
    juju = context.get_juju()
    result = juju.exec(f"scontrol --json show node {name}", unit=unit)
    return json.loads(result.stdout)


def node_name(unit: str) -> str:
    """Convert ``app/N`` into the Slurm node name ``app-N``."""
    return unit.replace("/", "-")


DENIAL_PATTERNS = (
    "permission denied",
    "access denied",
    "operation not permitted",
    "not permitted",
    "unauthorized",
    "invalid user",
    "must be root",
    "only root",
    "only user root",
    "only the root",
    "requested uid",
    "superuser",
    "super user",
    "insufficient privilege",
    "authentication required",
    "authentication is required",
    "only permitted by root",
)
"""Output fragments that indicate an authorization denial."""

IGNORE_PATTERNS = (
    "command not found",
    "no such file or directory",
    "usage:",
)
"""Output fragments that indicate the probe itself is broken rather than denied."""

def exec_as_user(
    context: Context, command: str, unit: str, user: str, wait: int | None = None
) -> Task:
    """Execute a command on a unit as an unprivileged user via sudo."""
    juju = context.get_juju()
    try:
        return juju.exec(f"sudo -u {user} sh -c {shlex.quote(command)}", unit=unit, wait=wait)
    except TaskError as e:
        return e.task


def assert_command_denied(result: Task, command: str, unit: str, user: str) -> None:
    """Assert a task run as an unprivileged user was denied on authorization grounds."""
    output = f"{result.stdout}\n{result.stderr}".lower()
    assert not result.success, (
        f"'{command}' as '{user}' on '{unit}' succeeded, expected denial: {result.stdout.strip()}"
    )
    assert not any(pattern in output for pattern in IGNORE_PATTERNS), (
        f"'{command}' as '{user}' on '{unit}' failed for a non-authorization reason "
        f"(broken probe, not a denial): {output.strip()}"
    )
    assert any(pattern in output for pattern in DENIAL_PATTERNS), (
        f"'{command}' as '{user}' on '{unit}' failed without a recognizable "
        f"denial message: {output.strip()}"
    )


class MailHandler:
    """SMTP server handler that captures the most recently received email."""

    def __init__(self) -> None:
        self.latest_email: EmailMessage = EmailMessage()

    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        mail_string = envelope.content.decode("utf8", errors="replace")
        self.latest_email = message_from_string(mail_string, policy=policy.default)
        return "250 Message accepted for delivery"

    def assert_mail(self, expected_to: str, subject_pattern: str, content_pattern: str) -> None:
        """Assert the latest email matches recipient, subject regex, and body regex."""
        self.assert_to(expected_to)
        self.assert_subject(subject_pattern)
        self.assert_content(content_pattern)

    def assert_content(self, pattern: str) -> None:
        part_count = 0
        for part in self.latest_email.iter_parts():
            part_count += 1
            ctype = part.get_content_type()
            content = part.get_content()
            assert ctype in ("text/plain", "text/html"), f"Unexpected content type: {ctype}"
            assert re.search(pattern, content, re.DOTALL), f"Pattern not found in {ctype} part"
        assert part_count == 2, f"Expected 2 parts in email, found {part_count}"

    def assert_subject(self, pattern: str) -> None:
        subject = self.latest_email["Subject"]
        assert re.match(pattern, subject), f"Subject '{subject}' doesn't match '{pattern}'"

    def assert_to(self, expected_to: str) -> None:
        actual_to = self.latest_email["To"]
        assert actual_to == expected_to, f"Expected '{expected_to}', got '{actual_to}'"


def interface_ipv4(interface: str) -> str:
    """Get the IPv4 address of ``interface``."""
    interfaces = net_if_addrs()
    if interface not in interfaces:
        raise ValueError(f"Invalid interface: '{interface}'. Available: {list(interfaces.keys())}")
    for addr in interfaces[interface]:
        if addr.family == socket.AF_INET:
            return addr.address
    raise RuntimeError(f"Interface '{interface}' exists but has no IPv4 address.")
