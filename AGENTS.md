# AGENTS.md

This file provides operating guidance for coding agents working in the Hush Line repository. We are a 501(c)(3) non-profit based in the United States, and this software is critical for our users' operational security, physical safety, and digital security.

## Principles

- Usability of the Software
- Authenticity of the Receiver
- Plausible Deniability of the Whistleblower
- Availability of the System
- Anonymity of the Whistleblower
- Confidentiality and Integrity of the Disclosures

## Core Users

- Message senders: whistleblowers, concerned citizens, engaged citizens, activists, students, bug bounty hunters.
- Message recipients: journalists and newsrooms, legal teams, employers and boards, educators and administrators, organizers and activists, software developers.
- Platform administrators

## Geographic Location

- Global; default to privacy-preserving choices across jurisdictions.

## Scope

- Applies to the entire repository unless a deeper `AGENTS.md` exists in a subdirectory.

## Project Priorities

- Preserve core whistleblower flow above all else.
- Core flow includes: send message.
- Core flow includes: E2EE defaults and behavior.
- Core flow includes: inbox visibility and message actions (status, delete, resend).
- Core flow includes: registration, login, and 2FA challenge.
- Prefer behavior-preserving changes over refactors unless explicitly requested.
- Keep privacy/security guarantees intact when editing routes, models, or settings.
- Accessibility score must be 100.
- Performance score must be 100.
- If accessibility/performance checks fail, re-run once before treating as a hard failure due to known test variability.

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

## Database / Docker Notes

- If tests fail with Postgres shared memory or recovery-mode errors, run `docker compose down -v` and rerun tests on a fresh stack.
- `dev_data` container is expected to exit after seeding.

## PR Guidance

- Include what changed.
- Include why it changed.
- Include validation commands run.
- Include known risks or follow-ups.
- Keep title specific and behavior-oriented.
