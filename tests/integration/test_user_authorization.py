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

"""BDD step definitions for Slurm user authorization tests.

Currently skipped because the scenarios have not yet been verified against
a live deployment. The shared unprivileged-user probe steps live in
`conftest.py`.
"""

import pytest
from pytest_bdd import scenarios

pytestmark = [
    pytest.mark.order(7),
    pytest.mark.skip(reason="security scenarios not yet verified against a live deployment"),
]

scenarios("features/slurm_user_authorization.feature")
