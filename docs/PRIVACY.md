# Hush Line Privacy Policy

Effective date: 2026-02-16

## Privacy Nutrition Facts

- **What you provide**: usernames, optional email, optional PGP key, and message content.
- **What we store**: encrypted message content plus the account and security records listed below.
- **What we share**: DigitalOcean hosts the service; Stripe handles billing if enabled.
- **Cookies**: an encrypted session cookie and a local flag for first‑visit anti‑censorship tips.
- **Your control**: update or delete your account and messages in the app.

## 1) Who We Are

Hush Line is a 501(c)(3) non-profit in the US. This policy explains how we handle data when you use Hush Line.

## 2) Data We Collect

- **Account records**: user ID, usernames, optional display name, optional bio, and profile visibility flags for directory and verification.
- **Security and auth data**: password hash, TOTP secret if enabled, and authentication logs with timestamp, success flag, and the TOTP code and timecode for successful 2FA logins. We do not store IP addresses or user‑agent strings in the database.
- **Messaging data**: message IDs, public IDs, reply slugs, message status, status change time, and message content stored as encrypted field values.
- **Profile field definitions**: custom field labels, types, required and enabled flags, choices, and sort order.
- **Notification settings**: email notification toggles and SMTP configuration such as server, port, username, password, sender, and encryption mode, stored encrypted at rest.
- **Invite codes**: invite code and expiration date when enabled.
- **Branding and guidance settings**: organization settings like brand name, logo, guidance prompts, and directory intro text.
- **Premium billing data**: Stripe customer ID, subscription IDs, status, period timestamps, invoice records with invoice ID, hosted invoice URL, total, status, created time, and Stripe webhook event payloads stored for processing.

For the database schema, see the models in [`hushline/model/`](https://github.com/scidsg/hushline/tree/main/hushline/model) such as
[`hushline/model/user.py`](https://github.com/scidsg/hushline/blob/main/hushline/model/user.py),
[`hushline/model/username.py`](https://github.com/scidsg/hushline/blob/main/hushline/model/username.py), and
[`hushline/model/message.py`](https://github.com/scidsg/hushline/blob/main/hushline/model/message.py).

## 3) How We Use Data

We use data strictly to operate Hush Line: account access, message delivery, encryption and notification settings, fraud and abuse prevention, and platform reliability. We do not use data for advertising.

## 4) Infrastructure & Third Parties

We rely on third‑party providers to run Hush Line:

- **DigitalOcean** for hosting and storage.
- **GitHub** for source control, issue tracking, and security advisories.
- **Terraform** for infrastructure provisioning and changes.

These providers may collect data as part of their services. We do not control their data practices; please review their policies.

If you enable email notifications, messages are sent via SMTP (either your custom SMTP settings or our configured provider). This transmits message content through email systems you choose or we operate.

If you enable premium billing, payment processing is handled by Stripe. We do not store full payment details.

## 5) Security

We encrypt stored message content and sensitive account fields (email, SMTP credentials, PGP key, TOTP secret). No system is perfectly secure, but we design Hush Line to minimize data exposure.

## 6) Retention & Deletion

Messages and accounts remain until you delete them. When you delete content, we remove it from active systems.

## 7) Cookies & Local Storage

We use an encrypted session cookie to keep you signed in. We also store a small local setting to show anti‑censorship tips for users on their first visit to the site. We do not use cookies for advertising or analytics.

## 8) Compliance & Legal Frameworks

We comply with applicable privacy and accessibility laws, including:

- General Data Protection Regulation (GDPR)
- California Consumer Privacy Act / California Privacy Rights Act (CCPA/CPRA)
- U.S. Federal Trade Commission Act (Section 5)
- Americans with Disabilities Act (ADA) and Section 508 (accessibility)

For GDPR processing, our legal bases may include performance of a contract, legitimate interests
in securing and operating the service, legal obligations, and consent where required.

## 9) Your Choices & Rights

You can exercise data rights in-product and by contacting us.

### GDPR (where applicable)

- Right of access
- Right to rectification
- Right to erasure
- Right to data portability
- Right to restriction or objection to processing
- Right to withdraw consent (where processing is based on consent)
- Right to lodge a complaint with your local data protection authority

### CCPA/CPRA (California residents, where applicable)

- Right to Know categories and specific pieces of personal information we collect, use, and disclose
- Right to Delete personal information, subject to applicable exceptions
- Right to Correct inaccurate personal information
- Right to Opt-Out of Sale/Sharing of personal information
- Right to Non-Discrimination for exercising privacy rights

We do not sell personal information and we do not share personal information for cross-context
behavioral advertising.

### Implementation Evidence (Code References)

The following source files implement rights-related functionality referenced in this policy:

- Data access/export (Right of Access / Right to Know / Data Portability):
  [`hushline/settings/data_export.py`](https://github.com/scidsg/hushline/blob/main/hushline/settings/data_export.py)
- Account deletion (Right to Erasure / Right to Delete):
  [`hushline/settings/delete_account.py`](https://github.com/scidsg/hushline/blob/main/hushline/settings/delete_account.py)
- Cascading deletion of related records:
  [`hushline/user_deletion.py`](https://github.com/scidsg/hushline/blob/main/hushline/user_deletion.py)
- Profile update flows (Rectification/Correction controls):
  [`hushline/settings/profile.py`](https://github.com/scidsg/hushline/blob/main/hushline/settings/profile.py)
- Cookie/session protection defaults:
  [`hushline/config.py`](https://github.com/scidsg/hushline/blob/main/hushline/config.py)

For requests that cannot be completed in-app, contact us and we will respond consistent with
applicable law.

## 10) Third-Party Policies

Our infrastructure and billing providers have their own privacy policies:

- DigitalOcean: https://www.digitalocean.com/legal/privacy-policy
- GitHub: https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement
- Terraform: https://www.hashicorp.com/privacy
- Stripe: https://stripe.com/privacy

## 11) Changes

We may update this policy and will post changes with a new effective date.

## 12) Contact

For privacy questions, contact us via Hush Line: https://tips.hushline.app/to/scidsg
