# Hush Line Threat Model

Last updated: 2026-02-15

This document models threats for Hush Line using publicly documented product behavior, deployment guidance, and published audit information.

## Security Objectives

- Protect submitter anonymity and plausible deniability.
- Preserve confidentiality and integrity of disclosures.
- Ensure recipients can verify destination authenticity.
- Maintain availability under realistic abuse and operational failure.
- Minimize retained sensitive data and blast radius on compromise.

## System Overview

Hush Line is a whistleblower/tip-line platform with two primary deployment models:

- Managed service (`tips.hushline.app`) with optional paid features.
- Personal Server / self-hosted variants, including Tor-only deployments.

Publicly documented properties include:

- End-to-end encryption path when recipients configure a public PGP key (browser-side encryption via OpenPGP.js).
- Server-side fallback encryption path when JavaScript is disabled.
- TLS in transit and encrypted data at rest.
- Tor onion access for site and app.
- Text-centric workflow (no general file intake in standard message flow).
- Optional message forwarding via SMTP and optional billing via Stripe.
- Human-verified recipient accounts in directory/verification flows.

## In-Scope Assets

- Message content and metadata (status, reply identifiers, timestamps).
- Recipient account credentials and authentication artifacts (password hash, optional 2FA secrets).
- Recipient encryption material (public PGP key and related settings).
- SMTP credentials and notification settings.
- Directory/profile data (display names, bios, custom fields, verification markers).
- Infrastructure/runtime secrets (encryption/session keys, DB credentials, API keys, tokens).
- Audit logs, CI/CD workflows, and software supply chain artifacts.

## Trust Boundaries

- Submitter browser/device -> public network/Tor -> Hush Line app edge.
- App layer -> database and object/blob storage.
- App layer -> SMTP provider (if forwarding enabled).
- App layer -> Stripe APIs/webhooks (if billing enabled).
- CI/CD and repository automation -> deployment/runtime environments.
- Directory and verification UX -> identity trust decisions by submitters.

## User Roles

- Submitter (usually unauthenticated).
- Recipient (authenticated account owner; free or paid tier).
- Platform administrators (service-side operational control).
- Verification staff (identity verification operations).
- Infrastructure operators (hosting, deployment, incident response).

## Adversaries

- Passive network observers (ISP, enterprise/school network, hostile hotspot).
- Active network attackers (MITM attempts, traffic manipulation, censorship).
- External web attackers (XSS, CSRF, SSRF, injection, auth bypass, abuse automation).
- Credential attackers (phishing, stuffing, brute force, session theft).
- Malicious or negligent insiders (recipient/admin/operator misuse).
- Supply-chain attackers (dependency compromise, CI workflow compromise).
- Legal/coercive adversaries (subpoenas, compelled disclosure, infrastructure seizure).
- Targeted deanonymization adversaries with substantial resources.

## Threat Scenarios and Mitigations

### 1) Deanonymization of submitters

Threats:

- Network-level identification on clearnet.
- Operational mistakes by submitters.
- Correlation via external services, endpoint telemetry, or timing.

Mitigations:

- Tor onion access for advanced anonymity needs.
- No submitter account requirement for message submission.
- Public guidance discouraging use of work-issued devices/networks.
- Minimize collection/retention of unnecessary identifying data.

Residual risk:

- User operational security errors remain a primary failure mode.
- Clearnet observers can still see that a user connected to Hush Line.

### 2) Message confidentiality compromise

Threats:

- Server/database compromise.
- Key or credential leakage.
- SMTP forwarding exposure in downstream systems.

Mitigations:

- Recipient-controlled PGP workflow for E2EE path.
- Encryption at rest and TLS in transit.
- Optional local decrypt workflow (Mailvelope integration) and Proton-focused key flow.
- Strong secret handling and key rotation procedures.

Residual risk:

- If recipients do not configure PGP/E2EE, operator or attacker exposure risk is higher.
- SMTP relay/storage can expand disclosure surface outside core app boundaries.

### 3) Recipient impersonation and destination trust failures

Threats:

- Users send disclosures to spoofed or fraudulent recipients.

Mitigations:

- Human-verified account badges and verification workflow.
- Directory UX that surfaces verification state.

Residual risk:

- Verification process quality is operationally sensitive.

### 4) Application-layer compromise

Threats:

- Injection vulnerabilities, SSRF, broken access control, CSRF/XSS regressions.

Mitigations:

- Framework-level protections, security headers/CSP, authz checks, tests, static checks, workflow security controls.
- Publicly documented independent audits (2024 and 2025) and remediation tracking.

Residual risk:

- Public 2025 audit summary reports unresolved findings (one medium, two low) that must be tracked to closure.

### 5) Availability and abuse

Threats:

- Spam/flooding, abusive submissions, resource exhaustion, infra outages.

Mitigations:

- Abuse controls in submission UX/flows (CAPTCHA, operational controls).
- CI checks for migration reliability and core regression prevention.
- Capacity planning and incident response runbooks.

Residual risk:

- Tor and anonymous access can limit traditional anti-abuse controls.

### 6) CI/CD and supply-chain compromise

Threats:

- Malicious workflow changes, unsafe interpolation in Actions, dependency CVEs.

Mitigations:

- Workflow security checks (actionlint and interpolation guardrails).
- Dependency security audit workflow for Python and Node.
- Pinned actions and repository protection with review requirements.

Residual risk:

- Zero-day dependency issues and compromised upstream packages remain possible.

## Known Public Audit Signals

- 2024 Subgraph report: two-phase review across personal-server/self-hosted and managed service architecture.
- 2025 Subgraph report (Dec 30, 2025): summary table lists:
  - V-001 Blind SSRF private-network enumeration (Medium, unresolved in report).
  - V-002 Client-side encryption timeout failure (Low, unresolved in report).
  - V-003 Sequential message IDs (Low, unresolved in report).

These findings should be treated as explicit risk register inputs until verified remediated.

## Non-Goals

- Guaranteeing perfect anonymity under nation-state-level endpoint compromise.
- Replacing high-opsec secure file drop systems designed for malicious-file handling workflows.

## Operational Requirements

- Mandatory review for security-sensitive code paths (auth, crypto, workflows, migrations).
- Routine dependency auditing and patch management.
- Secrets management with rotation and least privilege.
- Incident handling for vulnerability reports and coordinated disclosure.
- Continuous red-team-style validation of anonymity and metadata leakage assumptions.

## Data Minimization and Retention Principles

- Collect only data required for operation of messaging, account security, and optional billing.
- Keep optional features (SMTP forwarding, billing, directory profile detail) explicitly opt-in where possible.
- Provide account/message deletion paths and clear retention behavior.

## Open Risks to Track

- Close and verify remediation state for publicly reported unresolved audit findings.
- Continue hardening around SSRF and outbound request controls.
- Maintain robust encryption-failure handling and user-visible safety cues.
- Preserve anti-abuse controls without weakening anonymity guarantees.

## Sources (Public)

- https://hushline.app/
- https://tips.hushline.app/directory
- https://hushline.app/library/
- https://hushline.app/library/docs/getting-started/start-here/
- https://hushline.app/assets/files/2024-security-audit.pdf
- https://hushline.app/assets/files/2025-security-audit.pdf
- https://github.com/scidsg/hushline
- https://github.com/scidsg/hushline/blob/main/docs/PRIVACY.md
- https://github.com/scidsg/hushline/blob/main/SECURITY.md
