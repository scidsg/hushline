# Hush Line

[Hush Line](https://hushline.app) is an open source whistleblower platform for secure, anonymous, one-way disclosures to journalists, lawyers, and other trusted recipients.

Hosted service: <https://tips.hushline.app>  
Start here: <https://hushline.app/library/docs/getting-started/start-here/>

[![Accessibility](https://github.com/scidsg/hushline/actions/workflows/lighthouse.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/lighthouse.yml)
[![Performance](https://github.com/scidsg/hushline/actions/workflows/lighthouse-performance.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/lighthouse-performance.yml)
[![Run Linter and Tests](https://github.com/scidsg/hushline/actions/workflows/tests.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/tests.yml)
[![GDPR Compliance](https://github.com/scidsg/hushline/actions/workflows/gdpr-compliance.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/gdpr-compliance.yml)
[![CCPA Compliance](https://github.com/scidsg/hushline/actions/workflows/ccpa-compliance.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/ccpa-compliance.yml)
[![Database Migration Compatibility Tests](https://github.com/scidsg/hushline/actions/workflows/migration-smoke.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/migration-smoke.yml)
[![E2EE and Privacy Regressions](https://github.com/scidsg/hushline/actions/workflows/e2ee-privacy-regressions.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/e2ee-privacy-regressions.yml)
[![Workflow Security Checks](https://github.com/scidsg/hushline/actions/workflows/workflow-security.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/workflow-security.yml)
[![Python Dependency Audit](https://github.com/scidsg/hushline/actions/workflows/dependency-security-audit.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/dependency-security-audit.yml)
[![W3C Validators](https://github.com/scidsg/hushline/actions/workflows/w3c-validators.yml/badge.svg)](https://github.com/scidsg/hushline/actions/workflows/w3c-validators.yml)
[![Docs Screenshots](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/scidsg/hushline-screenshots/main/badge-docs-screenshots.json)](https://github.com/scidsg/hushline-screenshots/tree/main/releases/latest)

## Why Hush Line

Hush Line is built for safety-critical reporting workflows where trust, anonymity, and usability all matter. The project design priorities are:

- Usability of the software
- Authenticity of the receiver
- Plausible deniability of the whistleblower
- Availability of the system
- Anonymity of the whistleblower
- Confidentiality and integrity of disclosures

## Core Capabilities

| Area                   | What Hush Line Provides                                                                |
| ---------------------- | -------------------------------------------------------------------------------------- |
| Anonymous submissions  | No submitter account required for sending disclosures                                  |
| Encryption             | End-to-end encryption workflow with recipient PGP keys, plus server-side fallback path |
| Receiver trust         | Verified account workflow and trusted directory UX                                     |
| Account security       | Password authentication with optional TOTP 2FA                                         |
| Privacy access         | Tor onion support and privacy-preserving defaults                                      |
| Communication workflow | Message status management, one-way replies, and optional email forwarding modes        |
| Org customization      | Branding controls, onboarding guidance, and configurable profile fields                |
| Operational controls   | Strong CI checks, migration compatibility testing, and workflow security validation    |

## Quickstart (Local)

### 1) Clone and start

```sh
git clone https://github.com/scidsg/hushline.git
cd hushline
docker compose up
```

Open <http://localhost:8080>.

### 2) Common commands

| Command                                   | Purpose                                  |
| ----------------------------------------- | ---------------------------------------- |
| `make lint`                               | Run formatting/lint/type checks          |
| `make test`                               | Run full test suite with coverage output |
| `make fix`                                | Apply formatting/lint autofixes          |
| `make run-full`                           | Run Stripe-enabled development stack     |
| `docker compose down -v --remove-orphans` | Reset local Docker state                 |

## Security and Privacy

- Threat model: [`docs/THREAT-MODEL.md`](./docs/THREAT-MODEL.md)
- Security policy and vulnerability reporting: [`SECURITY.md`](./SECURITY.md)
- Privacy policy: [`docs/PRIVACY.md`](./docs/PRIVACY.md)

Report security issues through GitHub Security Advisories when possible, or via: <https://tips.hushline.app/to/hushline-security>.

## AI Coding Policy

Hush Line uses a risk-based model for AI-assisted development. Canonical policy: [`docs/AI-CODE-POLICY.md`](./docs/AI-CODE-POLICY.md).

Quick summary:

- Human-first is required for high-risk surfaces: funding work, databases/migrations, auth, payments, CI/CD, production infrastructure, and security/privacy boundary changes.
- AI-first is allowed for low-risk work such as scoped docs/process edits and isolated low-risk implementation tasks with clear rollback.
- If scope expands into high-risk areas (for example DB/auth/env/security), ownership immediately escalates to human-first.
- Ownership mode is tracked (`human-first` vs `ai-first`) with a quarterly operating target of roughly 70/30.
- Approved coding model policy is defined in [`AGENTS.md`](./AGENTS.md). As of 2026-02-13, the approved coding model is `gpt-5.3-codex xhigh`.

Policy discussion thread: <https://github.com/orgs/scidsg/discussions/1313>

## Contributor Checklist

Before opening a PR:

1. Read and follow [`AGENTS.md`](./AGENTS.md) (repository policy and safety-critical rules).
2. Check open Dependabot updates first, then handle applicable dependency/security updates.
3. Keep diffs minimal and behavior-preserving unless a behavior change is explicitly intended.
4. Add or update tests for every behavior change.
5. Run required checks locally:
   - `make lint`
   - `make test`
6. If behavior-critical paths changed, run CI-style coverage validation:

```sh
docker compose run --rm app poetry run pytest --cov hushline --cov-report term-missing -q --skip-local-only
```

7. Run dependency vulnerability audits:

```sh
poetry run pip-audit
npm audit --omit=dev
```

When frontend/runtime dependencies change, also run:

```sh
npm audit
```

8. Ensure commits are cryptographically signed and verifiable on GitHub.

## Documentation Map

- Docs index: [`docs/README.md`](./docs/README.md)
- Developer notes: [`docs/DEV.md`](./docs/DEV.md)
- Architecture: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- Runner automation: [`docs/RUNNERS.md`](./docs/RUNNERS.md)
- Terms: [`docs/TERMS.md`](./docs/TERMS.md)

## Latest Screenshots

<table>
  <tr>
    <td valign="bottom" width="73%">
      <img
        src="https://github.com/scidsg/hushline-screenshots/blob/main/releases/latest/guest/guest-directory-verified-desktop-light-fold.png?raw=true"
        width="100%"
        alt="Guest directory screenshot"
      />
    </td>
    <td valign="bottom" width="27%">
      <img
        src="https://github.com/scidsg/hushline-screenshots/blob/main/releases/latest/newman/auth-newman-onboarding-profile-mobile-light-fold.png?raw=true"
        width="100%"
        alt="Onboarding screenshot"
      />
    </td>
  </tr>
</table>

More screenshots: <https://github.com/scidsg/hushline-screenshots/tree/main/releases/latest>

## In the Media

- Privacy Guides: <https://www.privacyguides.org/posts/2026/01/09/hush-line-review-an-accessible-whistleblowing-platform-for-journalists-and-lawyers-alike/>
- Newsweek: <https://www.newsweek.com/protecting-free-speech-about-more-letting-content-run-wild-opinion-2012746>
- TIME: <https://time.com/7208911/psst-whistleblower-collective/>
- Around the Bend podcast: <https://www.youtube.com/watch?v=pO6q_t0wGGA&t=38m17s>

## Contributing and Conduct

Contributors are expected to follow the Code of Conduct:  
<https://github.com/scidsg/business-resources/blob/main/Policies%20%26%20Procedures/Code%20of%20Conduct.md>

## License

See [`LICENSE`](./LICENSE).
