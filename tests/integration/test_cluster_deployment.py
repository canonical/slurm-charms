# Copyright 2024-2026 Canonical Ltd.
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

"""Scenario bindings for the Slurm cluster deployment feature.

All steps in this feature are provided by the reusable ``pytest-jubilant-bdd``
handlers. Locally built charms are resolved from the ``<APP>_CHARM_PATH``
environment variables that ``repository.py integration`` exports.
"""

import pytest
from pytest_bdd import scenarios

# Cross-file ordering: the deploy scenario must run before every other
# feature since subsequent scenarios rely on the deployed cluster.
pytestmark = pytest.mark.order(1)

scenarios("features/slurm_cluster_deployment.feature")
