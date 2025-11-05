# Hush Line Security Policy

_Last updated: 2025-11-05_

Hush Line is free and open-source software maintained by Science & Design, Inc. We take coordinated disclosure seriously and operate with a bias toward rapid remediation and transparency.

Notable history: Hush Line has remediated CVEs related to CSP and security headers; see [CVE-2024-38522](https://nvd.nist.gov/vuln/detail/cve-2024-38522) and [CVE-2024-55888](https://nvd.nist.gov/vuln/detail/cve-2024-55888) for context. These were fixed in subsequent releases.

An external security review has been supported via the [Open Technology Fund](https://www.opentech.fund/security-safety-audits/hush-line-security-audit/) program. Future independent assessments are governed by the “Independent Security Assessments” section below.

---

## 1. Coordinated Vulnerability Disclosure (CVD)

- **Report channels**

  - Preferred: submit via our verified [Hush Line](https://tips.hushline.app/to/scidsg) tip page (supports anonymous reporting).
  - Alternative: open a private [GitHub](https://github.com/scidsg/hushline) Security Advisory draft on this repository.

- **Safe harbor**

  - Good-faith research, consistent with this policy and applicable law, will not be the basis for civil or criminal action initiated by us.

- **Scope**

  - In-scope: code and infrastructure in this repo and first-party hosted services under the `hushline.app` domain, including the tip submission service.
  - Out-of-scope examples: denial-of-service, rate limiting bypass without impact, speculative findings without proof-of-concept, social engineering of maintainers or users.

- **Vulnerability classes we care most about**

  - Authentication/authorization flaws, crypto misuse, XSS/HTML injection, CSRF, SSRF, template injection, insecure direct object reference, logic bugs affecting anonymity or confidentiality, supply-chain injection.

- **What to include**
  - A clear description, affected paths/versions, minimal reproducible steps or PoC, expected vs. actual behavior, impact assessment, and any logs/screens that help triage.

---

## 2. Triage & Response Objectives

- **Initial human response**: within 3 business days.
- **Triage + severity**: within 7 days, we’ll assign CVSS and determine exploitability.
- **Fix window (targets)**
  - Critical: 7 days
  - High: 14 days
  - Medium: 30 days
  - Low: 90 days

If exploitation in the wild is detected, we may hotfix and publish advisories immediately.

We generally issue GitHub Security Advisories and, when applicable, request a CVE assignment and reference affected and fixed versions in release notes.

---

## 3. Independent Security Assessments

- **Right to assess, not a maintenance guarantee**  
  Science & Design, Inc. may commission independent third-party security assessments of Hush Line at its discretion, including static/dynamic testing, configuration review, threat modeling, and privacy analysis. These assessments are not guaranteed services under any maintenance agreement.

- **Scope control**  
  Scope, methodology, data access, and test windows are defined by us to protect user privacy and service reliability. Testing that risks service stability will be isolated in staging environments unless otherwise authorized in writing.

- **Deliverables & disclosure**  
  We may share: (a) a high-level attestation or summary; (b) a redacted report; or (c) full report under NDA—at our sole discretion. Public disclosure, if any, occurs after remediation of high/critical issues.

- **No certification warranty**  
  Audit results are point-in-time and do not constitute a warranty of ongoing security or compliance fitness. Findings are triaged and tracked via our advisory process.

---

## 4. Cryptography & Data Protection

- End-to-end encryption for tip content; keys are never stored where they can be derived from plaintext submissions.
- Transport security: HTTPS/TLS enforced for all endpoints.
- Content Security Policy and security headers are enforced and regressions are treated as high severity in light of prior history.
- No plaintext secrets in code; repository and CI are scanned prior to release.

---

## 5. Dependency & Supply-Chain Security

- Automated dependency updates with review.
- Build artifacts are reproducible where feasible; pinned versions for critical transitive dependencies.
- Third-party JS is minimized, integrity-checked when externally loaded, and reviewed for license and security posture.

---

## 6. Secure Development Lifecycle (SDLC)

- Mandatory code review for security-relevant changes.
- Static analysis and linters on CI; security checks run per PR.
- Secrets pre-commit hooks; forbidden patterns in CI.
- Security test coverage for authN/authZ, crypto, and request handlers under `tests/`.

---

## 7. Infrastructure & Operations

- Managed hosting for application and databases with hardened configuration; infra-as-code defines baseline controls (network segmentation, backups, least-privilege).
- Separate staging environment for destructive testing; production changes require review and approver separation.
- Logs minimize sensitive data; retention is bounded; access is audited.

---

## 8. Incident Response

- Phases: detect → confirm → contain → eradicate → recover → learn.
- Notification: if a material security incident risks user data or anonymity, we will publish guidance and, when appropriate, in-product or site-wide notices.
- Post-mortems are written for high/critical incidents and may be public in summary form.

---

## 9. Privacy & Anonymity Guarantees

- Anonymous tip submission is a core requirement. We do not require PII to create an account or submit a tip. Use Tor/Onion services for additional network-layer protections when needed.

---

## 10. Hardening Expectations for Self-Hosts

If you deploy Hush Line yourself, you are responsible for:

- TLS with modern ciphers; HSTS; robust CSP; referrer policy; frame-ancestors.
- Regular updates to OS, runtime, and dependencies.
- Strong secrets management and key rotation.
- Isolated database with minimum privileges; backups with tested restores.

---

## 11. Versioning & Security Notes

Security-relevant changes are captured in releases and advisories. Review our Releases and the Security tab for patches and mitigation notes.

---

## 12. Contact

- Secure Disclosure: https://tips.hushline.app/to/scidsg
- Public: open a GitHub issue for non-sensitive questions
