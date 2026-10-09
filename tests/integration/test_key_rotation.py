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

"""BDD step definitions for Slurm key rotation."""

import json
import logging

import pytest
from constants import (
    SACKD_APP_NAME,
    SLURMD_APP_NAME,
    SLURMDBD_APP_NAME,
    SLURMRESTD_APP_NAME,
)
from jubilant import TaskError
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_jubilant_bdd import Context

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.order(10)

scenarios("features/slurm_key_rotation.feature")


@when(parsers.parse("I run action '{action}' on unit '{unit}' with an extended timeout"))
def run_action_extended_timeout(context: Context, action: str, unit: str) -> None:
    """Run an action, allowing extra time for the `slurmctld` restart it triggers."""
    juju = context.get_juju()
    # The rotate actions restart `slurmctld`, which can exceed the `juju run`
    # CLI's 60-second default wait: the model runs update-status hooks every 10
    # seconds, and actions are serialized behind them on the unit agent. The
    # reusable action step does not expose jubilant's `wait` parameter.
    try:
        result = juju.run(unit, action, wait=300)
    except TaskError as e:
        result = e.task

    context.action_results.push(result)


# ---------------------------------------------------------------------------
# Auth key rotation
# ---------------------------------------------------------------------------


@given(parsers.parse("I capture the slurm auth JWKS key from unit '{unit}'"))
def capture_auth_key(context: Context, unit: str) -> None:
    """Read ``/etc/slurm/slurm.jwks`` and store it in scenario state."""
    juju = context.get_juju()
    result = juju.exec("sudo cat /etc/slurm/slurm.jwks", unit=unit)
    context.scenario_state["initial_auth_key"] = json.loads(result.stdout)


@then(
    parsers.parse(
        "the slurm auth JWKS key on unit '{unit}' is rotated and propagated to all units"
    )
)
def auth_key_rotated(context: Context, unit: str) -> None:
    """Verify the auth key was rotated on the controller and propagated."""
    juju = context.get_juju()
    initial_key = context.scenario_state["initial_auth_key"]
    non_controller_units = [
        f"{SACKD_APP_NAME}/0",
        f"{SLURMD_APP_NAME}/0",
        f"{SLURMDBD_APP_NAME}/0",
        f"{SLURMRESTD_APP_NAME}/0",
    ]

    def ready(_ctx: Context) -> bool:
        try:
            result = juju.exec("sudo cat /etc/slurm/slurm.jwks", unit=unit)
            new_key = json.loads(result.stdout)
            assert len(new_key["keys"]) == 1
            assert new_key != initial_key
            for u in non_controller_units:
                r = juju.exec("sudo cat /etc/slurm/slurm.jwks", unit=u)
                key_entry = json.loads(r.stdout)
                assert len(key_entry["keys"]) == 1
                assert key_entry == new_key, f"auth key rotation failed on: {u}"
            assert juju.exec("sinfo", unit=f"{SACKD_APP_NAME}/0").success
            assert juju.exec("sinfo", unit=f"{SLURMD_APP_NAME}/0").success
            assert juju.exec("sacct", unit=unit).success
            assert juju.exec("scontrol token", unit=unit).success
            return True
        except Exception:
            return False

    context.wait(ready=ready)


# ---------------------------------------------------------------------------
# JWT key rotation
# ---------------------------------------------------------------------------


@given(parsers.parse("I capture the slurm JWT signing key from unit '{unit}'"))
def capture_jwt_key(context: Context, unit: str) -> None:
    """Read ``/etc/slurm/jwt_hs256.key`` and store it in scenario state."""
    juju = context.get_juju()
    result = juju.exec("sudo cat /etc/slurm/jwt_hs256.key", unit=unit)
    context.scenario_state.setdefault("jwt_keys", {})[unit] = result.stdout


@given(
    parsers.parse("the initial slurm JWT signing keys match between '{unit_one}' and '{unit_two}'")
)
def jwt_keys_match(context: Context, unit_one: str, unit_two: str) -> None:
    """Assert the initial JWT keys on two units are identical."""
    keys = context.scenario_state["jwt_keys"]
    assert keys[unit_one] == keys[unit_two], f"initial JWT key on {unit_one} and {unit_two} differ"


@given(parsers.parse("I capture an initial slurm JWT token from unit '{unit}'"))
def capture_initial_token(context: Context, unit: str) -> None:
    """Generate a Slurm JWT token and store it in scenario state."""
    juju = context.get_juju()
    token = juju.exec("sudo scontrol token lifespan=infinite", unit=unit).stdout.strip()
    context.scenario_state["initial_token"] = token


@given(parsers.parse("the slurmrestd diagnostic endpoints are reachable from '{unit}'"))
def discover_diag_endpoints(context: Context, unit: str) -> None:
    """Query the Slurm REST API openapi endpoint and find diagnostic paths."""
    juju = context.get_juju()
    scenario_state = context.scenario_state
    slurmrestd_unit = f"{SLURMRESTD_APP_NAME}/0"
    address = juju.status().apps[SLURMRESTD_APP_NAME].units[slurmrestd_unit].public_address
    base_url = f"http://{address}:6820"

    token = scenario_state["initial_token"]
    status_code, body = _api_get(juju, unit, token, f"{base_url}/openapi")
    assert status_code == "200", f"failed to query API with initial JWT key: {body}"
    endpoints = json.loads(body)
    assert "paths" in endpoints

    all_paths = endpoints["paths"].keys()
    slurm_diag = next(
        (p for p in all_paths if p.startswith("/slurm/") and p.endswith("/diag/")), None
    )
    slurmdb_diag = next(
        (p for p in all_paths if p.startswith("/slurmdb/") and p.endswith("/diag/")), None
    )
    assert slurm_diag is not None, "failed to find slurm diagnostic endpoint"
    assert slurmdb_diag is not None, "failed to find slurmdb diagnostic endpoint"

    scenario_state["base_url"] = base_url
    scenario_state["diag_urls"] = [f"{base_url}{slurm_diag}", f"{base_url}{slurmdb_diag}"]

    # Confirm initial token validity on both diagnostic endpoints.
    for url in scenario_state["diag_urls"]:
        code, _ = _api_get(juju, unit, token, url)
        assert code == "200", f"initial JWT key not functional at {url}"


@then(
    parsers.parse(
        "the slurm JWT signing key on unit '{unit}' is rotated and matches unit '{unit_two}'"
    )
)
def jwt_key_rotated(context: Context, unit: str, unit_two: str) -> None:
    """Poll until the JWT key is rotated and matches across units."""
    juju = context.get_juju()
    initial_controller = context.scenario_state["jwt_keys"][unit]
    cat_cmd = "sudo cat /etc/slurm/jwt_hs256.key"

    def ready(_ctx: Context) -> bool:
        try:
            new_controller = juju.exec(cat_cmd, unit=unit).stdout
            new_database = juju.exec(cat_cmd, unit=unit_two).stdout
            assert new_controller != initial_controller, "JWT key not rotated on controller"
            assert new_controller == new_database, (
                "JWT key on controller and database differ after rotation"
            )
            return True
        except Exception:
            return False

    context.wait(ready=ready)


@then(parsers.parse("the initial slurm JWT token from unit '{unit}' is no longer valid"))
def initial_token_invalid(context: Context, unit: str) -> None:
    """Verify the old token is rejected after key rotation."""
    juju = context.get_juju()
    token = context.scenario_state["initial_token"]
    url = context.scenario_state["diag_urls"][0]
    status_code, _ = _api_get(juju, unit, token, url)
    assert status_code != "200", f"old token still valid after rotation (HTTP {status_code})"


@then(
    parsers.parse(
        "a new slurm JWT token from unit '{unit}' is valid for all slurmrestd diagnostic endpoints"
    )
)
def new_token_valid(context: Context, unit: str) -> None:
    """Generate a new token and verify it works on all diagnostic endpoints."""
    juju = context.get_juju()
    new_token = juju.exec("sudo scontrol token lifespan=infinite", unit=unit).stdout.strip()
    for url in context.scenario_state["diag_urls"]:
        code, body = _api_get(juju, unit, new_token, url)
        assert code == "200", f"new JWT key not functional at {url}, got body: {body}"


# ---------------------------------------------------------------------------
# Helper: authenticated GET against the Slurm REST API
# ---------------------------------------------------------------------------


def _api_get(juju, unit: str, token: str, url: str) -> tuple[str, str]:
    """Execute an authenticated GET against the Slurm REST API."""
    result = juju.exec(
        f"export '{token}';"
        f" curl --silent --show-error"
        f" --write-out '\\nHTTP_RESPONSE_CODE:%{{http_code}}'"
        f" --header X-SLURM-USER-TOKEN:$SLURM_JWT"
        f" --request GET '{url}'",
        unit=unit,
    )
    assert "HTTP_RESPONSE_CODE:" in result.stdout, (
        f"no status code in response, stdout: {result.stdout} stderr: {result.stderr}"
    )
    body, status_line = result.stdout.strip().rsplit("HTTP_RESPONSE_CODE:", 1)
    return status_line.strip(), body
