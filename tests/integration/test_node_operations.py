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

"""BDD step definitions for Slurm node operations."""

import logging

import pytest
from pytest_bdd import parsers, scenarios, then
from pytest_jubilant_bdd import Context
from utils import node_name, scontrol_show_node

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.order(6)

scenarios("features/slurm_node_operations.feature")


def _wait_for_node(context: Context, unit: str, name: str, predicate) -> None:
    """Poll scontrol node output until ``predicate`` returns True."""

    def ready(_ctx: Context) -> bool:
        try:
            data = scontrol_show_node(context, unit, name)
            predicate(data)
            return True
        except Exception:
            return False

    context.wait(ready=ready)


# ``reason`` is double-quoted in the feature and may be empty (""), so
# ``parsers.re`` with ``[^"]*`` is used rather than ``parsers.parse`` whose
# default ``(.+)`` requires at least one character.
_NODE_STATE_RE = (
    r"the slurmd node for unit '(?P<unit>[^']+)' has state containing '(?P<state>[^']+)' "
    r'and reason "(?P<reason>[^"]*)"'
)

_NODE_WEIGHT_RE = (
    r"the slurmd node for unit '(?P<unit>[^']+)' has weight '(?P<weight>[^']+)' "
    r"and state containing '(?P<state>[^']+)' "
    r'and reason "(?P<reason>[^"]*)"'
)


@then(parsers.re(_NODE_STATE_RE))
def node_state_and_reason(context: Context, unit: str, state: str, reason: str) -> None:
    """Assert a compute node's state contains ``state`` and its reason matches."""
    name = node_name(unit)

    def check(data):
        assert state in data["nodes"][0]["state"], (
            f"expected state containing '{state}', got '{data['nodes'][0]['state']}'"
        )
        assert data["nodes"][0]["reason"] == reason, (
            f"expected reason '{reason}', got '{data['nodes'][0]['reason']}'"
        )

    _wait_for_node(context, unit, name, check)


@then(parsers.re(_NODE_WEIGHT_RE))
def node_weight_state_and_reason(
    context: Context, unit: str, weight: str, state: str, reason: str
) -> None:
    """Assert a compute node's weight, state, and reason all match."""
    name = node_name(unit)

    def check(data):
        assert data["nodes"][0]["weight"] == int(weight), (
            f"expected weight {weight}, got '{data['nodes'][0]['weight']}'"
        )
        assert state in data["nodes"][0]["state"]
        assert data["nodes"][0]["reason"] == reason

    _wait_for_node(context, unit, name, check)
