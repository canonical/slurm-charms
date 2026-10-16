#!/usr/bin/env python3
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

"""BDD step definitions for Slurm secret and credential protection tests.

Currently skipped because the scenarios have not yet been verified against
a live deployment. The shared unprivileged-user probe steps live in
`conftest.py`.
"""

import logging
import shlex

import pytest
from pytest_bdd import parsers, scenarios, then
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.order(8),
    pytest.mark.skip(reason="security scenarios not yet verified against a live deployment"),
]

scenarios("features/slurm_secret_and_credential_protection.feature")


@then(parsers.parse("the file '{path}' on unit '{unit}' has mode '{mode}'"))
def file_has_mode(context: Context, path: str, unit: str, mode: str) -> None:
    """Assert a file on a unit has the expected octal permission mode."""
    juju = context.get_juju()
    result = juju.exec(f"stat -c '%a' {shlex.quote(path)}", unit=unit)
    assert result.success, f"cannot stat '{path}' on '{unit}': {result.stderr.strip()}"
    actual = result.stdout.strip()
    assert actual == mode, f"'{path}' on '{unit}' has mode '{actual}', expected '{mode}'"


@then(parsers.parse("the file '{path}' on unit '{unit}' is owned by user '{user}'"))
def file_is_owned_by_user(context: Context, path: str, unit: str, user: str) -> None:
    """Assert a file on a unit is owned by the expected system user."""
    juju = context.get_juju()
    result = juju.exec(f"stat -c '%U' {shlex.quote(path)}", unit=unit)
    assert result.success, f"cannot stat '{path}' on '{unit}': {result.stderr.strip()}"
    actual = result.stdout.strip()
    assert actual == user, f"'{path}' on '{unit}' is owned by '{actual}', expected '{user}'"
