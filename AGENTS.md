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

The live public website and verified directory also show recurring recipient patterns that agents should keep in mind when writing copy, shaping features, or evaluating regressions:

- Investigative reporters, editors, documentary teams, and nonprofit newsrooms using public profiles to receive source outreach.
- Whistleblower counsel, public-interest law firms, and legal intake teams handling fraud, corruption, retaliation, and misconduct reports.
- Corporate, nonprofit, and project governance contacts such as boards, ethics offices, and public accountability channels.
- Security researchers, bug bounty teams, software maintainers, and platform security contacts receiving vulnerability reports.
- Privacy, anti-censorship, digital rights, and open-source infrastructure organizations receiving sensitive tips from the public.
- Educators, school administrators, and campus-adjacent trusted adults offering safer reporting channels to students and families.
- Organizers, advocacy groups, and issue-specific nonprofits coordinating protected first contact around harms, retaliation, detention, or abuse.
- Organizations that need shared or role-based intake points in addition to individual profiles, such as board inboxes or security-reporting addresses.

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

## Example Use Cases (Non-Exhaustive)

| As a...           | I need to...                                                        | So...                                                                      |
| ----------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Lawyer            | Make myself discoverable                                            | Whistleblowers can find me by location                                     |
| Lawyer            | Add a rich bio                                                      | Whistleblowers know how I can help them                                    |
| Lawyer            | Add links to my website                                             | Sources can verify who I am                                                |
| Lawyer            | Have multiple aliases                                               | I can have clean intake channels for different investigations              |
| Lawyer            | Add custom message statuses                                         | I can let the person who submitted a message know next steps for their tip |
| Whistleblower     | Easily find someone who can help                                    | I can work toward making a positive change                                 |
| Whistleblower     | Contact someone without creating my own account                     | I can submit a tip without any friction or requirements                    |
| Whistleblower     | Know the status of my tip                                           | I understand what my next steps are                                        |
| Whistleblower     | Find a verified tip line                                            | I have high confidence in the person or organization I intend to reach     |
| Journalist        | Make it easy for a source to contact me without requiring a new app | I receive better tips from more people                                     |
| Journalist        | Add more info (Signal, email, contact page, social profiles, etc.)  | Sources have options for how to contact me                                 |
| Journalist        | Add more info (Signal, email, contact page, social profiles, etc.)  | Sources have additional social proof before contacting me                  |
| Journalist        | Add my Hush Line profile URL to websites and profiles               | Sources have confidence that I really own that tip line                    |
| Business          | Provide my employees a trusted tip line                             | I receive tips while maintaining confidentiality and source privacy        |
| Business (EU)     | Set up an external method of employee reporting                     | My company remains compliant with the Whistleblowing Directive of 2019     |
| Business          | Provide a public tip line                                           | My company can receive messages about fraud, waste, and abuse              |
| Business          | Offer employees a safe tip line                                     | I can help establish a culture of safe reporting                           |
| Software Engineer | Have a way of receiving vulnerability reports                       | I can quickly address risks to users or data                               |
| Manager           | Give my direct reports a way to share concerns privately            | I can reinforce a safe workplace and psychological safety                  |

Additional public-directory-grounded use cases agents should recognize:

| As a...                        | I need to...                                                        | So...                                                                 |
| ------------------------------ | ------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Investigative newsroom         | Publish a verified tip line and profile URL                         | Sources can confirm they are contacting the real newsroom             |
| Investigative reporter         | Add clear beats and contact context to my profile                   | Sources know whether I cover their issue before they reach out        |
| Documentary project            | Offer a private intake channel to participants and witnesses        | People can share sensitive experiences without a public backchannel   |
| Whistleblower law firm         | Separate intake by matter, practice area, or campaign              | Potential clients reach the right reporting address faster            |
| Security team                  | Publish a verified security-reporting address                       | Researchers know where to send vulnerability disclosures              |
| Open-source or privacy project | Offer a public reporting endpoint without requiring a new app       | Community members can report risks with less friction                 |
| Board or ethics contact        | Maintain a shared governance inbox                                  | People can report concerns to the correct oversight body              |
| School or university contact   | Publish distinct reporting addresses for different campus concerns  | Students, staff, and families do not have to guess where to report    |
| Advocacy nonprofit             | Receive sensitive reports from affected communities                 | People can ask for help without exposing themselves unnecessarily     |
| Support organization           | Provide a safe first-contact channel for retaliation or detention   | People can share time-sensitive information with less operational risk |

Additional ISO 37002-grounded use cases agents should recognize:

| As a...                            | I need to...                                                            | So...                                                                            |
| ---------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Employee or volunteer              | Report wrongdoing outside my management chain                           | I still have a credible path to raise concerns if my manager is conflicted       |
| Contractor, supplier, or partner   | Report misconduct linked to an organization I work with                 | Serious issues are not missed just because I am not a direct employee            |
| Whistleblower                      | Use a reporting channel that is visible, accessible, and secure         | I can raise a concern without procedural friction or unsafe workarounds          |
| Whistleblower                      | Receive acknowledgement, follow-up, and timely feedback                 | I understand that my report is moving and what to expect next                    |
| Whistleblower                      | Report confidentially or anonymously where allowed                      | I can reduce the risk of exposure while still sharing what I know                |
| Organization                       | Offer at least one reporting path distinct from normal management lines | People can report concerns even when local leadership is implicated              |
| Organization                       | Triage reports by urgency, severity, and risk of detriment             | High-risk cases and whistleblower safety needs are handled first                 |
| Organization                       | Protect whistleblowers and other involved parties from retaliation       | Speaking up does not create preventable personal or workplace harm               |
| Organization                       | Give reporters a way to continue communication after the initial report | The case can progress without forcing unsafe or ad hoc follow-up methods         |
| Organization                       | Support vulnerable reporters with appropriate communication and process  | Children, migrants, and others at higher risk are not excluded by the workflow   |
| Investigation team                 | Preserve confidentiality on a strict need-to-know basis                 | Evidence can be handled without unnecessarily exposing identities                |
| Governing body or compliance lead  | Measure response times, case outcomes, and trust in the system          | The reporting program can be improved based on actual performance                |

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
  - Runner processes one open issue from the `Hush Line Roadmap` project column `Agent Eligible`, top to bottom.
- Human-PR guard:
  - Runner exits early if any open human-authored PR exists.
- One-bot-PR guard:
  - Runner exits early if any unrelated open PR exists from bot login (`HUSHLINE_BOT_LOGIN`, default `hushline-dev`).
  - Exception: when the selected issue is a child of a GitHub parent epic, the runner may allow the long-lived epic PR plus the matching child issue PR, and should stop only for unrelated bot PRs.
- Required runner behavior:
  - At runner start, perform a full local environment reset and seed sequence:
    - `docker compose down -v --remove-orphans`
    - Stop/remove all Docker containers (`docker rm -f $(docker ps -aq)`)
    - Kill listener processes on configured runner ports (`HUSHLINE_DAILY_KILL_PORTS`, default `4566 4571 5432 8080`)
    - `docker compose up -d --build`
    - `docker compose run --rm dev_data`
  - Run required validation checks locally before opening PRs (`make lint`, `make test`).
  - Persist per-run logs in `docs/agent-logs/` and include the log path in PR context.
  - Use signed commits that verify on GitHub.
  - Force-sync local checkout to `origin/main` at runner start to clear dirty trees.
  - If the selected issue is a child of a GitHub parent epic, create/update the child issue branch as usual, but target its PR at the shared epic branch instead of `main`.
  - The shared epic branch should be the only long-lived PR that targets `main` for that epic.
  - Move the selected issue's project status to `In Progress` while work is underway.
  - Move the selected issue's project status to `Ready for Review` after the PR is open.
  - For child PRs that target an epic branch, do not rely on GitHub auto-close keywords alone; the child issue must be explicitly closed when that PR is merged into the epic branch.
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
  - Python: `make audit-python`
  - Node runtime deps: `make audit-node-runtime`
  - Run full Node audit when frontend/runtime dependencies change: `make audit-node-full`
- If local dependency-audit commands are blocked by environment/network issues, document the failure reason in the PR and require a passing `Dependency Security Audit` workflow before merge.
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
  - `gpt-5.4 high`
- Unapproved models must not be used to author or modify production code without explicit changes to this document.
- Unapproved autonomous agent frameworks or services, including OpenClaw or similar issue/PR-driving agents, must not comment on Issues, open PRs, trigger repository workflows, or otherwise act on behalf of maintainers without explicit approval documented in this file or a linked maintainer-approved PR/Issue.
- Public issue comments, triage, or repository automation from external autonomous agents are disallowed by default. If such tooling is proposed, it must first be reviewed for moderation, security, and operational risk before any repository interaction is enabled.
- If an approved model is unavailable, stop and do not substitute another model unless this document is updated first.
- If an agent believes another model should be approved, an Issue must be opened with clear rationale. Data must support the request.
  - Do not open any Issues without meeting the requirements above.

## Database / Docker Notes

- If tests fail with Postgres shared memory or recovery-mode errors, run `docker compose down -v` and rerun tests on a fresh stack.
- Before starting issue work, run `./scripts/agent_issue_bootstrap.sh`, which performs:
  - `docker compose build`
  - `docker compose down -v --remove-orphans`
  - `docker compose up -d postgres blob-storage`
  - `docker compose run --rm dev_data`
- On macOS, `agent_issue_bootstrap.sh` attempts to start Docker Desktop and waits up to `HUSHLINE_DOCKER_START_TIMEOUT_SECONDS` (default `180`).
- `dev_data` container is expected to exit after seeding.

## Documentation

When behavior changes or features are added/removed, update relevant documentation in `docs/`.

## PR Guidance

- Before opening a PR, always run `make lint` and `make test` and fix any issues first.
- Before requesting merge, ensure the PR branch is conflict-free with `main` (for example, `git fetch origin && git rebase origin/main`). If the branch changes, rerun `make lint` and `make test`.
- All commits must be cryptographically signed (GPG or SSH signing) and verifiable on the remote.
- Include what changed.
- Include why it changed.
- Include validation commands run.
- Include manual testing steps for every PR, even if the manual check is "not applicable" with a brief reason.
- Include known risks or follow-ups.
- If PR scope changes after opening, update the PR description so it reflects the final state before merge.
- Keep title specific and behavior-oriented.
- Check when the PR was created and explicitly flag if it appears stale or no longer relevant before proceeding.
- Never interpolate untrusted GitHub event text fields (issue/PR/comment title or body) directly in shell `run:` steps in workflows.
- Enforce branch protection required checks before merge: `Workflow Security Checks`, CodeQL scanning, and `Run Linter and Tests`.
