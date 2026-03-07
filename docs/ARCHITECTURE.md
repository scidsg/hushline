# Release and Deployment Architecture

Human-owned only (non-agentic): release and infrastructure control plane.

```text
                                                 +-----------------------------------------+
                                                 | scidsg/hushline                         |
                                                 | 1) bump hushline/version.py             |
                                                 | 2) create release tag (vX.Y.Z)          |
                                                 +-------------------+---------------------+
                                                                     |
                                                                     v
                                                 +-----------------------------------------+
                                                 | build-release.yml                       |
                                                 | publish hushline/hushline:vX.Y.Z image  |
                                                 +-------------------+---------------------+
                                                                     |
                      +-----------------------+----------------------+-------------------------------------------------+
                      |                                              |                                                 |
                      v                                              v                                                 v
  +-----------------------------------------+   +------------------------------------------+   +--------------------------------------------+
  | STAGING                                 |   | PRODUCTION                               |   | SINGLE TENANT INSTANCES                    |
  | trigger path                            |   | trigger path                             |   | trigger path                               |
  | scidsg/hushline-infra                   |   | Terraform Cloud workspace: prod          |   | Terraform Cloud workspace:                 |
  | - edit hushline-env/hushline.tf tag     |   | - manually set VCS branch to vX.Y.Z      |   | - hushline-infra-ENV_NAME                  |
  | - merge to main (workspace: staging)    |   | - manually start/confirm apply run       |   | - manually set VCS branch to vX.Y.Z        |
  |                                         |   |                                          |   | - manually start/confirm apply run         |
  +-------------------+---------------------+   +-------------------+----------------------+   +-------------------+------------------------+
                      |                                             |                                              |
                      v                                             v                                              v
      +-----------------------------------+         +-----------------------------------+          +-----------------------------------+
      | Terraform apply (staging)         |         | Terraform apply (prod)            |          | Terraform apply (tenant env)      |
      | - DO App Platform app             |         | - DO App Platform app             |          | - DO App Platform app             |
      | - managed Postgres (pg16)         |         | - managed Postgres (pg16)         |          | - managed Postgres (pg16)         |
      | - Spaces bucket + CORS            |         | - Spaces bucket + CORS            |          | - Spaces bucket + CORS            |
      +-----------------------------------+         +-----------------------------------+          +-----------------------------------+
```

Automated follow-on release actions:

- `.github/workflows/bump-staging-after-release.yml` opens or updates a PR in `scidsg/hushline-infra` so staging tracks the released image tag.
- `.github/workflows/bump-personal-server-after-release.yml` opens or updates a PR in `scidsg/hushline-personal-server` so the package version and bundled app image track the released image tag.
- `.github/workflows/docs-screenshots-after-release.yml` is the release-triggered orchestrator for website screenshots. It waits for the released GHCR image, then calls `.github/workflows/docs-screenshots.yml` to capture screenshots and `.github/workflows/publish-docs-screenshots.yml` to sync them into `scidsg/hushline-website` via a dedicated automation branch and PR. The workflow attempts to merge that PR immediately so the website repo keeps the latest screenshots at `src/assets/img/screenshots/` and archives `src/assets/img/screenshots/releases/latest/` plus `src/assets/img/screenshots/releases/vX.Y.Z/`.
- `.github/workflows/public-directory-weekly-report.yml` can run weekly or on demand, fetches `https://tips.hushline.app/directory/users.json`, filters to opted-in public Hush Line users, compares against both the last sync and the most recent snapshot from at least 7 days earlier, then syncs `scidsg/hushline-stats` via a dedicated automation branch and PR. The workflow attempts to merge that PR immediately after generating the `README.md`, latest aliases, and timestamped historical JSON/Markdown reports.
