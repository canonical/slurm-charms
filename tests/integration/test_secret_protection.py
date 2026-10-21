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

"""BDD step definitions for Slurm secret and credential protection tests."""

import logging
import shlex

import pytest
from pytest_bdd import parsers, scenarios, then
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.order(8)

scenarios("features/slurm_secret_and_credential_protection.feature")


@then(parsers.parse("the file '{path}' on unit '{unit}' has mode '{mode}' and owner '{user}'"))
def file_has_mode_and_owner(context: Context, path: str, unit: str, mode: str, user: str) -> None:
    """Assert a file on a unit has the expected octal permission mode and owning user."""
    juju = context.get_juju()
    result = juju.exec(f"stat -c '%a %U' {shlex.quote(path)}", unit=unit)
    assert result.success, f"cannot stat '{path}' on '{unit}': {result.stderr.strip()}"
    actual_mode, actual_user = result.stdout.strip().split()
    assert (actual_mode, actual_user) == (mode, user), (
        f"'{path}' on '{unit}' has mode '{actual_mode}' and owner '{actual_user}', "
        f"expected mode '{mode}' and owner '{user}'"
    )
