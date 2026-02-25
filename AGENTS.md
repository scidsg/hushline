# AGENTS.md

This file provides operating guidance for coding agents working in the Hush Line repository. We are a 501(c)(3) non-profit based in the United States, and consider this software safety-critical infrastructure protecting users’ operational, physical, and digital security.

## Principles

- Usability of the Software
- Authenticity of the Receiver
- Plausible Deniability of the Whistleblower
- Availability of the System
- Anonymity of the Whistleblower
- Confidentiality and Integrity of the Disclosures

## Core Users

| Message Senders    | Message Recipients           | Administrators          |
| ------------------ | ---------------------------- | ----------------------- |
| Whistleblowers     | Journalists and Newsrooms    | Platform Administrators |
| Concerned citizens | Lawyers and Law Offices      |                         |
| Engaged citizens   | Employers and Boards         |                         |
| Activists          | Educators and Administrators |                         |
| Students           | Organizers and Activists     |                         |
| Bug bounty hunters | Software developers          |                         |

## Geographic Location

- Global; default to privacy-preserving choices across jurisdictions.

## Scope

- Applies to the entire repository unless a deeper `AGENTS.md` exists in a subdirectory.

## Project Priorities

- Preserve core whistleblower flow above all else.
- Prefer behavior-preserving changes over refactors unless explicitly requested.
- Keep privacy/security guarantees intact when editing routes, models, or settings.
- Accessibility score must be 100.
- Performance score must be >=95.

### Core Flows

| Unauthenticated Users         | Authenticated, All Users             | Authenticated, Paid Users        | Authenticated, Admin Users                    |
| ----------------------------- | ------------------------------------ | -------------------------------- | --------------------------------------------- |
| Send a message                | Send a message                       | Cancel subscription              | Update directory intro text                   |
| Register/login, 2FA challenge | E2EE defaults and behavior           | Resubscribe to Super User tier   | Change primary color                          |
| Browse user directory         | View messages in Inbox               | Add/remove an Alias              | Change app name                               |
| Search Verified tab           | Change message status                | Add/remove custom profile fields | Upload new logo                               |
| Search All tab                | Delete a message                     |                                  | Hide donation link                            |
| E2EE defaults and behavior    | Resend message to email (if enabled) |                                  | Customize profile header                      |
|                               | Upgrade to Super User                |                                  | Change homepage; Enable/disable User Guidance |
|                               | Add PGP key via Proton Key Lookup    |                                  | Update Emergency Exit link                    |
|                               | Add PGP key manually                 |                                  | Update prompt heading/body                    |
|                               | Add display name                     |                                  | Add new prompt                                |
|                               | Add bio                              |                                  | Enable/disable new registrations              |
|                               | Add additional profile fields        |                                  | Enable/disable registration code gating       |
|                               | Opt in to user directory             |                                  | Make user account admin                       |
|                               | Change username/password             |                                  | Verify a primary user account                 |
|                               | Enable/disable 2FA                   |                                  | Verify an alias user account                  |
|                               | Download account data                |                                  | Delete a user account                         |
|                               | Delete own user account              |                                  |                                               |
|                               | Validate Raw Email Headers           |                                  |                                               |
|                               | Add an image to Vision for OCR       |                                  |                                               |
|                               | View Tools tab in nav                |                                  |                                               |

## Local Commands

- Start stack: `docker compose up`
- Issue bootstrap (required before issue work): `./scripts/agent_issue_bootstrap.sh`
- Lint: `make lint`
- Tests: `make test`
- Coverage (CI-style): `docker compose run --rm app poetry run pytest --cov hushline --cov-report term-missing -q --skip-local-only`

## Automation Runners

- Runner docs: `docs/AGENT_RUNNER.md`
- Daily issue runner script: `scripts/agent_daily_issue_runner.sh`
- Daily issue eligibility:
  - Daily issue automation processes one open issue labeled `agent-eligible` or `low-risk`.
- One-bot-PR guard:
  - Runner exits early if any open PR exists from bot login (`HUSHLINE_BOT_LOGIN`, default `hushline-dev`).
- Required runner behavior:
  - Start each issue attempt with the issue bootstrap sequence:
    - `docker compose down -v --remove-orphans`
    - `docker compose up -d postgres blob-storage`
    - `docker compose run --rm dev_data`
  - Run required validation checks locally before opening PRs (`make lint`, `make test`, plus runner-specific checks).
  - Use signed commits that verify on GitHub.
  - Force-sync local checkout to `origin/main` at runner start to clear dirty trees.
  - Return to `main` after PR creation.

## Required Checks Before PR

- `make lint` passes
- Full `make test` for all changes
- If touching behavior-critical code, run CI-style coverage command above

## Testing Expectations

- Add or update tests for every behavior change.
- Prefer tests that lock in user-visible behavior and security-critical outcomes.
- For notification/email changes, validate all three modes: generic notification only, include message content, encrypt entire email body.
- For encryption changes, ensure client-side encryption is covered and server-side fallback (JS disabled or no client payload) is covered.
- For any change touching templates, static JS/CSS, response headers, or external integrations, add/update tests to verify CSP remains enforced and is not broadened unintentionally (for example in tests/test_security_headers.py).
- If a CSP directive/source must be broadened, document explicit maintainer approval and risk rationale, and add tests that lock the change to the minimal required scope.

## Change Guidelines

- Keep diffs minimal and focused.
- Do not silently change UX flows without explicit request.
- Avoid changing production behavior just to satisfy coverage; add tests first.
- If non-test code changes are needed for testability, document why in PR description.

## Security and Privacy Requirements

- Treat all whistleblower data paths as security-critical.
- Do not weaken E2EE behavior, encryption defaults, or anonymization controls.
- Insecure flags are explicitly disallowed in commands, scripts, CI, Docker, and documentation examples.
  - Never use or suggest flags that disable signature, TLS/certificate, keyring, or encryption protections (for example: `--insecure-storage`, `--no-sign`, `--no-verify`, `--allow-unauthenticated`, `--insecure`, `--skip-verify`, `--tls-skip-verify`, `--disable-encryption`).
  - Never bypass supply-chain or integrity controls with flags such as `--ignore-signatures`, `--trusted-host`, or equivalent unless there is a formally documented emergency exception approved by maintainers.
  - If a task appears to require any such flag, stop and ask for a security review path instead of proceeding.
- Run dependency vulnerability checks before PR:
  - Python: `poetry run pip-audit`
  - Node runtime deps: `npm audit --omit=dev`
  - Run full Node audit when frontend/runtime dependencies change: `npm audit`
- If a CVE is found in reachable runtime code, block merge until fixed or formally risk-accepted.
- For security-related changes, include in PR:
  - threat or risk summary
  - affected data paths
  - mitigation and tests added
- Never log secrets, plaintext disclosures, private keys, or sensitive tokens.

## Dependabot Triage Priority

- Before starting any new non-dependency work, check for open Dependabot updates (PRs/issues/security alerts).
- If Dependabot updates exist, review upstream release notes/changelogs/security advisories first.
- Determine what applies to Hush Line (runtime, build, CI, tests, and operational/security impact).
- Address applicable updates before starting unrelated work.
- If an update is deferred, document why, residual risk, and follow-up plan in the PR description.

## Approved Models

- Only approved models may be used for code changes.
- Approved models:
  - `gpt-5.3-codex xhigh`
- Unapproved models must not be used to author or modify production code without explicit changes to this document.
- If an approved model is unavailable, stop and do not substitute another model unless this document is updated first.
- If an agent believes another model should be approved, an Issue must be opened with clear rationale. Data must support the request.
  - Do not open any Issues without meeting the requirements above.

## Database / Docker Notes

- If tests fail with Postgres shared memory or recovery-mode errors, run `docker compose down -v` and rerun tests on a fresh stack.
- Before starting issue work, run the issue bootstrap sequence via `./scripts/agent_issue_bootstrap.sh`.
- `dev_data` container is expected to exit after seeding.

## Documentation

When behavior changes or features are added/removed, update documentation in `docs/`.

## PR Guidance

- Before opening a PR, always run `make lint` and `make test` and fix any issues first.
- Before requesting merge, ensure the PR branch is conflict-free with `main` (for example, `git fetch origin && git rebase origin/main`). If the branch changes, rerun `make lint` and `make test`.
- All commits must be cryptographically signed (GPG or SSH signing) and verifiable on the remote.
- Include what changed.
- Include why it changed.
- Include validation commands run.
- Include known risks or follow-ups.
- If PR scope changes after opening, update the PR description so it reflects the final state before merge.
- Keep title specific and behavior-oriented.
- Check when the PR was created and explicitly flag if it appears stale or no longer relevant before proceeding.
- Never interpolate untrusted GitHub event text fields (issue/PR/comment title or body) directly in shell `run:` steps in workflows.
- Enforce branch protection required checks before merge: `Workflow Security Checks`, CodeQL scanning, and `Run Linter and Tests`.
