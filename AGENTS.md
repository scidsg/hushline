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
| Search Verified tab           | Change message status                | View Vision tab in nav           | Upload new logo                               |
| Search All tab                | Delete a message                     | Add an image to Vision for OCR   | Hide donation link                            |
| E2EE defaults and behavior    | Resend message to email (if enabled) | Add/remove custom profile fields | Customize profile header                      |
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

## Local Commands

- Start stack: `docker compose up`
- Lint: `make lint`
- Tests: `make test`
- Coverage (CI-style): `docker compose run --rm app poetry run pytest --cov hushline --cov-report term-missing -q --skip-local-only`

## Required Checks Before PR

- `make lint` passes
- Full `make test` for all changes
- If touching behavior-critical code, run CI-style coverage command above

## Testing Expectations

- Add or update tests for every behavior change.
- Prefer tests that lock in user-visible behavior and security-critical outcomes.
- For notification/email changes, validate all three modes: generic notification only, include message content, encrypt entire email body.
- For encryption changes, ensure client-side encryption is covered and server-side fallback (JS disabled or no client payload) is covered.

## Change Guidelines

- Keep diffs minimal and focused.
- Do not silently change UX flows without explicit request.
- Avoid changing production behavior just to satisfy coverage; add tests first.
- If non-test code changes are needed for testability, document why in PR description.

## Security and Privacy Requirements

- Treat all whistleblower data paths as security-critical.
- Do not weaken E2EE behavior, encryption defaults, or anonymization controls.
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

## Approved Models

- Only approved models may be used for code changes.
- Approved OpenAI models (as of 2026-02-13):
  - `gpt-5.3-codex` (primary/default for coding tasks)
- Unapproved models must not be used to author or modify production code without explicit changes to this document.
- If an approved model is unavailable, stop and do not substitute another model unless this document is updated first.
- If an agent believes another model should be approved, an Issue must be opened with clear rationale. Data must support the request.
  - Do not open any Issues without meeting the requirements above.

## Database / Docker Notes

- If tests fail with Postgres shared memory or recovery-mode errors, run `docker compose down -v` and rerun tests on a fresh stack.
- `dev_data` container is expected to exit after seeding.

## Documentation

When behavior changes or features are added/removed, update documentation:

Local workflow:

1. Clone docs repo:
   - `git clone https://github.com/scidsg/hushline-docs.git` (if missing)
   - `cd hushline-docs && git pull --ff-only`
   - Update, add, or remove relevant documentation content.
2. Build docs:
   - `cd docs`
   - `npm run build`
3. Clone or update website repo:
   - `cd ..`
   - `git clone https://github.com/scidsg/hushline-website.git` (if missing)
   - `cd hushline-website && git pull --ff-only`
4. Sync built docs into website library:
   - `rsync -a --delete ../hushline-docs/docs/build/ ../hushline-website/src/library/`
5. Verify the site renders correctly before opening PRs.

## PR Guidance

- Before opening a PR, always run `make lint` and `make test` and fix any issues first.
- Include what changed.
- Include why it changed.
- Include validation commands run.
- Include known risks or follow-ups.
- Keep title specific and behavior-oriented.
- Check when the PR was created and explicitly flag if it appears stale or no longer relevant before proceeding.
- Never interpolate untrusted GitHub event text fields (issue/PR/comment title or body) directly in shell `run:` steps in workflows.
- Enforce branch protection required checks before merge: `Workflow Security Checks`, CodeQL scanning, and `Run Linter and Tests`.
