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
  | EPHEMERAL STAGING                       |   | PRODUCTION                               |   | SINGLE TENANT INSTANCES                    |
  | trigger path                            |   | trigger path                             |   | trigger path                               |
  | internal pull request                   |   | Terraform Cloud workspace: prod          |   | Terraform Cloud workspace:                 |
  | - maintainer adds `staging` label       |   | - manually set VCS branch to vX.Y.Z      |   | - hushline-infra-ENV_NAME                  |
  | - isolated PR workspace and DO project  |   | - manually start/confirm apply run       |   | - manually set VCS branch to vX.Y.Z        |
  | - remove label to destroy; 24h maximum  |   |                                          |   | - manually start/confirm apply run         |
  +-------------------+---------------------+   +-------------------+----------------------+   +-------------------+------------------------+
                      |                                             |                                              |
                      v                                             v                                              v
      +-----------------------------------+         +-----------------------------------+          +-----------------------------------+
      | Terraform apply (PR staging)      |         | Terraform apply (prod)            |          | Terraform apply (tenant env)      |
      | - isolated DO App Platform app    |         | - DO App Platform app             |          | - DO App Platform app             |
      | - disposable Postgres 16 HA       |         | - managed Postgres (pg16)         |          | - managed Postgres (pg16)         |
      | - no DNS, Spaces, or prod secrets |         | - Spaces bucket + CORS            |          | - Spaces bucket + CORS            |
      +-----------------------------------+         +-----------------------------------+          +-----------------------------------+
```

Automated follow-on release actions:

- `.github/workflows/staging_deploy.yml` creates staging only when a maintainer adds the `staging` label to an internal pull request. It deploys from a trusted temporary branch into an isolated, 24-hour Terraform workspace, runs HTTPS/browser/onion smoke checks, and destroys the environment when the label is removed or the pull request closes.
- `.github/workflows/bump-personal-server-after-release.yml` opens or updates a PR in `scidsg/hushline-personal-server` so the package version and bundled app image track the released image tag.
- `.github/workflows/docs-screenshots.yml` is the release and manual entrypoint for screenshots. On published releases it waits for the released GHCR image, scans Hush Line docs plus `scidsg/hushline-website` for referenced screenshot paths, captures only that generated allowlist, and then calls `.github/workflows/publish-docs-screenshots.yml` to publish the standalone archive to `scidsg/hushline-screenshots` and the current website screenshots to `scidsg/hushline-website`. Both publishes push directly to the target repository default branch without opening PRs. The website sync only updates `src/assets/img/screenshots/current/`, while the screenshots repo keeps the used-only standalone release archive and badge.
- `.github/workflows/public-directory-weekly-report.yml` can run weekly or on demand, fetches `https://tips.hushline.app/directory/users.json`, filters to opted-in public Hush Line users, compares against both the last sync and the most recent snapshot from at least 7 days earlier, then syncs `scidsg/hushline-stats` via a dedicated automation branch and PR. The workflow attempts to merge that PR immediately after generating the `README.md`, latest aliases, and timestamped historical JSON/Markdown reports.

Operational setup and use are documented in
[Ephemeral pull-request staging](./EPHEMERAL-STAGING.md).

## Application Data and Encryption Boundaries

Hush Line separates one-way disclosure intake from account conversation
follow-up.

- Public tip submissions use recipient PGP keys for encrypted intake and keep
  the no-account sender path available.
- Anonymous submissions use the message inbox and reply/status link flow; they
  do not create account conversations.
- Logged-in senders and recipients can use two-way account conversations when
  both sides have active, signing-capable Hush Line chat keys.
- Conversation plaintext is encrypted and decrypted in the browser. The server
  stores per-participant encrypted message copies, participant records,
  timestamps, unread/activity state, and generic notification state.
- New conversation replies require all participants to have chat public
  encryption keys and chat public signing keys before the server accepts the
  append request.
- Conversation notifications are generic activity alerts; plaintext and
  ciphertext are not copied into notification email.

See [Two-way chat end-to-end encryption](./TWO-WAY-CHAT-E2EE.md) for the
feature-specific security model.
