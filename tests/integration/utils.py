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

from __future__ import annotations

import json
import logging
import os
import re
import socket
from email import message_from_string, policy
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from psutil import net_if_addrs

logger = logging.getLogger(__name__)

# Mirror the LOCAL_* environment variables used by the legacy conftest so the
# BDD deploy step can pick up locally built charms without code duplication.
LOCAL_CHARMS = {
    "sackd": os.getenv("LOCAL_SACKD"),
    "slurmctld": os.getenv("LOCAL_SLURMCTLD"),
    "slurmd": os.getenv("LOCAL_SLURMD"),
    "slurmdbd": os.getenv("LOCAL_SLURMDBD"),
    "slurmrestd": os.getenv("LOCAL_SLURMRESTD"),
}


def local_charm_path(charm: str) -> Path | str:
    """Return the local charm path for ``charm`` if set, else the charm name."""
    value = LOCAL_CHARMS.get(charm)
    return Path(value) if value else charm


def scontrol_show_node(context, unit: str, name: str) -> dict[str, Any]:
    """Run ``scontrol --json show node <name>`` on ``unit`` and return parsed JSON."""
    juju = context.get_juju()
    result = juju.exec(f"scontrol --json show node {name}", unit=unit)
    return json.loads(result.stdout)


def node_name(unit: str) -> str:
    """Convert ``app/N`` into the Slurm node name ``app-N``."""
    return unit.replace("/", "-")


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
