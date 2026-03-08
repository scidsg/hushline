# Hush Line Threat Model

## Overview

Hush Line is an open‑source whistleblower/tip‑line platform for secure, anonymous, one‑way disclosures. A Flask backend serves public submission pages and authenticated inboxes, backed by Postgres, optional S3/FS blob storage, and optional Stripe billing. Submissions are encrypted using recipient PGP keys (client‑side OpenPGP.js in `assets/js/client-side-encryption.js` with server‑side fallback in `hushline/model/field_value.py`), and sensitive account data is encrypted at rest via `hushline/crypto.py` and `hushline/model/user.py`. Tor onion support and privacy‑preserving defaults make anonymity a core objective.

Primary assets include:

- Disclosure content and metadata (message status, reply slugs, timestamps).
- Recipient accounts, password hashes, 2FA secrets, session identifiers.
- Recipient PGP keys, SMTP credentials, and notification settings.
- Public directory/profile data and verification markers.
- Encryption/session secrets (`ENCRYPTION_KEY`, `SESSION_FERNET_KEY`) and service API keys (SMTP, Stripe).
- Billing records, audit logs, and automation artifacts.

## Threat model, Trust boundaries and assumptions

### Trust boundaries

- **Submitter browser → Hush Line app:** anonymous POSTs to `/to/<username>` and other public endpoints (`hushline/routes/profile.py`).
- **Recipient session → Hush Line app:** authenticated inbox/settings routes (`hushline/routes/*`, `hushline/settings/*`).
- **Admin session → Hush Line app:** privileged settings/admin actions (`hushline/admin.py`, `hushline/settings/branding.py`).
- **App → Postgres:** ORM‑mediated data access (`hushline/db.py`, `hushline/model/*`).
- **App → Blob storage:** S3 or filesystem driver (`hushline/storage.py`).
- **App → External services:** SMTP (`hushline/email.py`), Stripe (`hushline/premium.py`), Proton key lookup (`hushline/routes/onboarding.py`, `hushline/settings/proton.py`), DNS lookups for email header tooling (`hushline/email_headers.py`), and scheduled directory refreshes (`hushline/public_record_refresh.py`, `hushline/securedrop_directory_refresh.py`).
- **CI/CD → Runtime:** dependency and workflow supply chain.

### Assumptions

- HTTPS/Tor is correctly configured; onion services should not set HSTS (handled in `hushline/__init__.py`).
- Operators protect secrets and infrastructure; compromise of `ENCRYPTION_KEY` or DB access is catastrophic for confidentiality.
- Client‑side encryption is only as trustworthy as the JS served to the submitter; a compromised server or build pipeline can bypass E2EE.
- Submitter endpoint compromise and traffic correlation by powerful adversaries remain out of scope; operational security guidance is required.

### Input control

- **Attacker‑controlled:** HTTP requests (forms, headers, query params), message content, profile/bio fields, PGP keys submitted by users, raw email headers tool input, and unauthenticated webhook traffic.
- **Operator‑controlled:** environment variables and deploy‑time config (keys, SMTP/Stripe credentials, storage endpoints), admin settings (branding, guidance text), and scheduled refresh jobs.
- **Developer‑controlled:** migrations, CLI tooling (`cli_reg.py`, `cli_stripe.py`), tests, build scripts.

## Attack surface, mitigations and attacker stories

### Key attack surfaces & mitigations

1. **Anonymous submission & reply flows** (`routes/profile.py`, `model/field_value.py`):

   - Math CAPTCHA (`validate_captcha`) and WTForms validation limit abuse; field lengths are capped for encrypted payloads.
   - PGP key required for accepting submissions; client‑side OpenPGP encryption plus server‑side fallback; padded ciphertext reduces length inference.
   - Reply slug is randomly generated (~51 bits, `crypto.gen_reply_slug`). Treat reply links as secrets.

2. **Authentication & session management** (`routes/auth.py`, `auth.py`, `secure_session.py`, `config.py`):

   - Passwords hashed with scrypt (`model/user.py`); 2FA via TOTP with basic rate‑limit in `routes/auth.py`.
   - Encrypted session cookie (`SESSION_FERNET_KEY`) with `__Host-` naming, `Secure`, `HttpOnly`, and `SameSite=Strict` settings.
   - Server‑side `session_id` stored per user to invalidate sessions on logout/password change.

3. **Settings and admin surfaces** (`settings/*`, `admin.py`):

   - CSRF protection via Flask‑WTF and explicit CSRF validation in admin endpoints.
   - Input validation (length limits, canonical HTML, `safe_template`, profanity filters) and file upload constraints for branding.
   - High‑privilege functions (tier updates, delete user) guarded by `admin_authentication_required`.

4. **Directory and profile rendering** (`routes/directory.py`, `md.py`, `safe_template.py`):

   - Markdown and HTML are sanitized with Bleach; templates rely on Jinja auto‑escaping plus CSP (`hushline/__init__.py`).
   - Public directory JSON is read‑only; opt‑in visibility via `show_in_directory`.

5. **Outbound connectivity / SSRF** (`settings/common.py`, `email.py`, `settings/notifications.py`):

   - URL verification rejects non‑HTTPS and private/loopback IPs, including DNS resolution checks.
   - SMTP host validation prevents connections to non‑public IP ranges and localhost.

6. **Stripe billing** (`premium.py`):

   - Webhooks are verified with Stripe signatures; events are deduplicated in `StripeEvent`.
   - Authenticated endpoints manage subscription state.

7. **Storage access** (`storage.py`):

   - `send_from_directory` protects against path traversal; S3 uses pre‑signed URLs for private objects.
   - Public assets are stored under fixed keys (e.g., branding logo) to reduce path control risk.

8. **Security headers and CSP** (`hushline/__init__.py`):

   - CSP, HSTS (non‑onion), X‑Frame‑Options, Referrer‑Policy, and Permissions‑Policy are set on all responses.

9. **Email header tooling** (`routes/email_headers.py`, `email_headers.py`):
   - Untrusted header input is size‑limited and DNS queries are time‑boxed.

### Attacker stories (examples)

- **Stored XSS via profile/directory fields:** An attacker attempts to inject script into bios or guidance text to steal recipient sessions or deanonymize usage. Mitigations include Bleach sanitization, `safe_template`, and CSP; any bypass would be high impact.
- **Account takeover through brute force:** An attacker scripts logins against recipient accounts. Strong passwords and 2FA help, but login endpoints lack global rate limiting; exposure depends on password reuse and 2FA adoption.
- **Unauthorized message access:** An attacker guesses message identifiers or reply slugs to read messages. Access controls join messages to authenticated usernames (`routes/message.py`); reply slugs are random but should be treated as secrets.
- **SSRF via URL verification or SMTP settings:** A malicious user tries to reach internal services by registering verification URLs or SMTP servers. Host/IP checks mitigate, but DNS rebinding or IPv6 edge cases should be reviewed.
- **Billing fraud:** Forged Stripe webhooks could alter tiers if signature verification or webhook secret is misconfigured. `premium.py` mitigates with Stripe signature checks.
- **Supply‑chain compromise of client‑side encryption:** If JS dependencies or build artifacts are compromised, attacker could exfiltrate plaintext before encryption. CI security audits and pinned dependencies reduce risk but cannot eliminate it.
- **Operator compromise:** A hostile operator or cloud breach can access DB and keys, defeating server‑side encryption. Client‑side encryption mitigates but relies on JS integrity and user opsec.

## Criticality calibration (critical, high, medium, low)

**Critical** — breaks confidentiality/anonymity across many users or yields full system control.

- RCE, SQL injection, or auth bypass leading to mass disclosure access.
- Theft of `ENCRYPTION_KEY` or DB credentials, enabling decryption of stored PII and message content.
- Widespread client‑side encryption bypass (malicious JS or compromised build pipeline).

**High** — compromise of a single recipient account or privileged settings; significant privacy impact.

- Stored XSS in inbox/profile/admin templates leading to session theft or CSRF.
- Privilege escalation to admin via broken access control.
- SSRF to internal services (metadata endpoints, internal admin panels).
- Forged Stripe webhooks altering billing/tier state or enabling paid features without auth.

**Medium** — scoped impact or requires additional user interaction.

- CSRF that toggles notification settings or profile visibility.
- Information leakage through predictable reply slugs or directory enumeration.
- Denial‑of‑service on submission or email‑header tooling.

**Low** — minor leaks or misconfigurations with limited impact.

- UI‑only issues, verbose error messages, or non‑sensitive data exposure.
- Vulnerability classes requiring attacker control that is not present (e.g., filesystem path traversal in `storage.py` where paths are not user‑controlled in normal flows, or CLI‑only issues requiring shell access).

Severity is calibrated toward confidentiality/anonymity: even a small XSS or access‑control bug can become high‑impact in a whistleblower context. Conversely, issues that require operator misconfiguration or developer‑only access are generally reduced in severity but should still be documented for hardening.
