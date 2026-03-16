# Python 3.13 Upgrade Readiness

Study date: March 16, 2026

## Recommendation

Go, but only as a phased migration.

The current repository state does not show a lockfile-level dependency blocker for Python 3.13. The main unresolved risk is execution-path validation: Hush Line's Docker images, Docker-backed test jobs, and the host-based lint workflow are still pinned to Python 3.12 and therefore do not yet provide a Python 3.13 signal.

This is not ready for a direct production flip today. It is ready for a narrow implementation spike that updates version pins and runs the normal validation gates on Python 3.13 before any merge.

## Current Pin Inventory

| Surface                   | Current state                                     | Evidence                                  |
| ------------------------- | ------------------------------------------------- | ----------------------------------------- |
| Poetry runtime constraint | `python = "^3.11"` already permits 3.13           | `pyproject.toml`                          |
| Static type checking      | `python_version = "3.12"`                         | `pyproject.toml`                          |
| Dev container base image  | `python:3.12.6-slim-bookworm`                     | `Dockerfile.dev`                          |
| Prod container base image | `python:3.12.6-slim-bookworm`                     | `Dockerfile.prod`                         |
| CI host Python for lint   | `python-version: "3.12"`                          | `.github/workflows/tests.yml`             |
| CI test execution path    | `make test`, which runs through Docker by default | `Makefile`, `.github/workflows/tests.yml` |

## Dependency Readiness Summary

The locked dependency graph contains 77 packages.

- 61 packages are pure-Python or universal-wheel packages.
- 16 packages ship platform-specific wheels.
- No locked package declares an upper Python bound below 3.13.

Critical compiled or runtime-sensitive dependencies already show Python 3.13 support signals in `poetry.lock`:

| Package          | Locked version | 3.13 signal                        | Notes                                                     |
| ---------------- | -------------- | ---------------------------------- | --------------------------------------------------------- |
| `aiohttp`        | `3.13.3`       | `cp313` wheels present             | Async HTTP stack appears ready.                           |
| `SQLAlchemy`     | `2.0.37`       | `cp313` wheels present             | ORM layer appears ready.                                  |
| `greenlet`       | `3.1.1`        | `cp313` wheels present             | Marker allows Python `<3.14`; acceptable for 3.13.        |
| `psycopg-binary` | `3.2.4`        | `cp313` wheels present             | Postgres binary package appears ready.                    |
| `pysequoia`      | `0.1.25`       | `cp313` wheels present             | Important because Hush Line relies on OpenPGP behavior.   |
| `cryptography`   | `46.0.5`       | `abi3` wheels present              | Uses ABI-stable wheels rather than `cp313`-named wheels.  |
| `ruff`           | `0.4.10`       | platform `py3-none` wheels present | Tooling package still needs actual lint-job confirmation. |

No lockfile entry currently looks like a hard stop for Python 3.13. The remaining work is validation, not broad dependency churn.

## Blockers

| Severity | Blocker                                                                        | Impact                                                                                                                                               | Proposed resolution                                                                                                |
| -------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| High     | Docker base images are still pinned to Python 3.12.6.                          | Local development, production image builds, and Docker-backed test jobs cannot exercise Python 3.13 yet.                                             | Update both Dockerfiles to the same Python 3.13 slim-bookworm tag in a spike branch and rerun standard validation. |
| High     | CI lint is still pinned to host Python 3.12.                                   | The fastest feedback path (`poetry install`, `mypy`, `ruff`) has no Python 3.13 coverage today.                                                      | Update `.github/workflows/tests.yml` to `python-version: "3.13"` in the spike.                                     |
| Medium   | `mypy` is configured for Python 3.12 semantics.                                | Type checking can miss or misreport Python-version-specific issues during the migration.                                                             | Change `tool.mypy.python_version` to `3.13` in the same spike branch.                                              |
| High     | Native dependency install paths remain unverified on the 3.13 Bookworm images. | `pysequoia`, `cryptography`, `psycopg`, `greenlet`, and their build/runtime requirements are security-critical and must be proven on the real image. | Rebuild dev/prod images and run `make test` after the pin changes.                                                 |
| Medium   | Audit results are only known for the current lock state.                       | If the resolver changes anything while moving to 3.13, new reachable CVEs could enter the runtime graph.                                             | Run `make audit-python` only if the Python 3.13 spike changes the lockfile.                                        |

## Required Validation For The Spike

Run these unchanged repository targets after the 3.13 pin update:

1. `make lint`
2. `make test`
3. `make audit-python` only if `poetry.lock` changes

If the spike touches container images only and the lockfile stays stable, the expected work is mostly compatibility verification rather than package upgrades.

## Effort Estimate

- Best case: about 1 engineering day
- Likely case: 1 to 2 engineering days
- Worst case: 3 days if Python 3.13 exposes native-build, typing, or test-order issues

That estimate assumes:

- the dependency lock remains mostly unchanged
- failures, if any, are limited to version pins, typing configuration, or a small number of package updates
- no encryption, auth, or migration behavior needs code changes

## Rollout Plan

Use a phased rollout, not a single blind switch.

1. Open a narrow implementation PR that updates only:
   - `Dockerfile.dev`
   - `Dockerfile.prod`
   - `.github/workflows/tests.yml`
   - `pyproject.toml` (`tool.mypy.python_version`)
2. Avoid dependency upgrades unless the Python 3.13 resolver forces them.
3. Run `make lint` and `make test`.
4. Run `make audit-python` if `poetry.lock` changes.
5. If validation stays green, merge the Python 3.13 migration as one focused change.
6. If validation fails, stop and split the discovered incompatibilities into follow-up fixes before retrying the version bump.

## Proposed Follow-up Issues

1. `[Implementation] Migrate runtime and CI pins from Python 3.12 to Python 3.13`
   Prerequisites: none beyond this study
   Scope: Dockerfiles, CI lint workflow, `mypy` target version, validation results

2. `[Fix] Resolve Python 3.13 regressions discovered during migration spike`
   Prerequisites: only create if the spike fails
   Scope: package upgrades, typing fixes, Docker/native build fixes, or test updates required by the spike

## Decision Summary

Python 3.13 looks feasible for Hush Line.

The dependency inventory supports proceeding, and no obvious package-level blocker is visible in the locked graph. The migration should still be treated as a phased, validation-first change because Hush Line's security-sensitive runtime depends on native packages and Docker-backed execution paths that are not yet pinned to Python 3.13.
