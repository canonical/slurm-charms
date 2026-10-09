# Slurm charms BDD integration tests

BDD integration tests for the Slurm charms, using
[`pytest-jubilant-bdd`](https://github.com/canonical/pytest-jubilant-bdd) and
[`gherkinator`](https://github.com/canonical/gherkinator).

## Layout

```
tests/integration/
├── features/                                  # Generated .feature files
├── plans/edge.yaml                            # SOURCE OF TRUTH (gherkinator plan)
├── conftest.py                                # Pytest config + shared fixtures
├── constants.py                               # Test constants
├── utils.py                                   # Shared helpers
└── test_*.py                                  # Step definitions (one per feature)
```

The `.feature` files in `features/` are generated from `plans/edge.yaml`. Do
not hand-edit them — they are overwritten on every `gherkinator generate`.

## Key principles

- **`plans/edge.yaml` is the single source of truth.** Edit it, then validate
  and regenerate.
- **`pytest-jubilant-bdd` provides the session-scoped `context` fixture** in
  place of a hand-rolled `juju` fixture. Access the harness via
  `context.get_juju()`.
- **No step handler imports.** The plugin auto-registers handlers via its
  `pytest11` entry point. Import only `Context`, `assertions`, etc. from
  `pytest_jubilant_bdd` when authoring custom steps.
- **`context.wait()` replaces `tenacity`.** Custom Then steps poll via
  `context.wait(ready=...)`.
- **Cross-file ordering** is preserved via `pytestmark = pytest.mark.order(N)`
  on each `test_*.py` module.

## Workflow

```bash
# Edit the plan
$EDITOR tests/integration/plans/edge.yaml

# Validate + regenerate
gherkinator validate tests/integration/plans/edge.yaml
gherkinator generate --format gh tests/integration/plans/edge.yaml \
    --output-dir tests/integration/features

# Run
pytest tests/integration/ -v
```

Install gherkinator via snap (`sudo snap install gherkinator --classic`) or
build from source.

## Feature overview

| Feature | Risk | Status | Order | Step definitions |
|---|---|---|---|---|
| Slurm cluster deployment | edge | implemented | 1 | `test_cluster_deployment.py` |
| Slurm services health | edge | implemented | 2 | `test_services_health.py` |
| Slurm node operations | edge | implemented | 6 | `test_node_operations.py` |
| Slurm key rotation | edge | implemented | 10 | `test_key_rotation.py` |
| Slurm job submission | edge | implemented | 12 | `test_job_submission.py` |
| Slurm mail notifications | edge | implemented | 14 | `test_mail.py` |
| Slurm OCI runtime | edge | implemented | 13 | `test_oci_runtime.py` |
| Slurm InfluxDB accounting | edge | planned | 12 | `test_influxdb.py` (skipped) |
| Slurmctld high availability | edge | implemented | 19 | `test_ha.py` (HA-gated) |

A `status: planned` feature is not yet green; `status: implemented` features
are. Re-run `gherkinator generate` after changing the status so the `.feature`
file picks up the corresponding tag.

## Custom steps

Custom steps live in the `test_*.py` modules for behavior the framework
doesn't cover: cluster deploy quirks, `scontrol --json` parsing, port/metrics
checks, key rotation introspection, GPU mock device setup, mail capture via
`aiosmtpd`, and HA controller discovery.