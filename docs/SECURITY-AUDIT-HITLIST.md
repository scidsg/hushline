# Hush Line Security Audit Hitlist (Issue #1359)

Last updated: 2026-02-24
Audience: External professional security audit firm (Subgraph-targeted pre-engagement scope)

This document is preparation-only scope guidance for a human security audit. It prioritizes AGENTS core flows, current codebase risk surfaces, and explicit regression retests for publicly tracked findings.

## 1) Prioritized Audit Hitlist (P0/P1/P2)

### HL-AUD-P0-001

- Test ID: `HL-AUD-P0-001`
- Priority: `P0`
- Feature/flow: CSRF protections on state-changing routes.
- Threat hypothesis: One or more POST mutations can be triggered cross-site without a valid CSRF token.
- Preconditions:
  - `WTF_CSRF_ENABLED=true`.
  - Authenticated normal user and authenticated admin user.
  - Premium-enabled and premium-disabled deployments.
- Steps:
  1. Enumerate all mutation routes (`POST`) from app routes and blueprints.
  2. Attempt same-site valid-token mutation and record baseline.
  3. Replay each mutation with missing token, malformed token, and cross-origin form post.
  4. Include these high-risk paths: `/premium/*` mutations, `/message/*/(delete|status|resend)`, `/settings/delete-account`, `/settings/alias/*/delete`, `/admin/*` mutations.
  5. Verify state in DB before/after each request.
- Expected secure behavior: Missing/invalid CSRF token requests are rejected and state does not change.
- Failure indicators: Any state mutation succeeds without a valid token.
- Evidence to collect:
  - Route inventory and tested request matrix.
  - Request/response capture for pass/fail cases.
  - Before/after DB records showing mutation/no-mutation.
- Suggested remediation owner: Backend security owner.

### HL-AUD-P0-002

- Test ID: `HL-AUD-P0-002`
- Priority: `P0`
- Feature/flow: Stored/DOM XSS in directory and search rendering.
- Threat hypothesis: User-controlled profile content can execute script in search rendering paths.
- Preconditions:
  - Accounts with controllable `display_name`/`bio` via profile settings.
  - JS-enabled browser testing.
  - Directory verified tab enabled and disabled variants.
- Steps:
  1. Seed profile values containing harmless XSS markers in `display_name` and `bio`.
  2. Validate server-rendered `/directory` and `/to/<username>` output escaping.
  3. Trigger client-side search rendering via `/directory/users.json` and `assets/js/directory.js` / `assets/js/directory_verified.js` paths.
  4. Inspect DOM mutation sinks and verify no executable HTML injection occurs during highlighting/search.
  5. Repeat for Verified and All tabs.
- Expected secure behavior: Untrusted content remains inert text in all render states.
- Failure indicators: Script execution, event-handler execution, or injected DOM nodes from user data.
- Evidence to collect:
  - Browser video + console/network logs.
  - DOM snapshots before/after search.
  - Payload set used (redacted to harmless markers in report body).
- Suggested remediation owner: Frontend + Backend.

### HL-AUD-P0-003

- Test ID: `HL-AUD-P0-003`
- Priority: `P0`
- Feature/flow: Authentication/authorization boundary and object-ownership enforcement.
- Threat hypothesis: IDOR or privilege bypass allows cross-tenant access/modification.
- Preconditions:
  - At least three users: `user-a`, `user-b`, `admin`.
  - Aliases and messages for both non-admin users.
- Steps:
  1. As `user-a`, attempt to read/update/delete/resend/status-change `user-b` message `public_id`s.
  2. As `user-a`, attempt alias operations using `user-b` alias IDs.
  3. As non-admin, attempt admin-only routes and mutations.
  4. Validate whether route responses leak object existence across tenants.
- Expected secure behavior: Strict ownership checks and admin-only enforcement; unauthorized actions denied.
- Failure indicators: Cross-tenant data access, mutation success, or privilege escalation.
- Evidence to collect:
  - Request/response set by actor role.
  - DB object ownership checks.
  - Access-control decision table.
- Suggested remediation owner: Backend authz owner.

### HL-AUD-P0-004

- Test ID: `HL-AUD-P0-004`
- Priority: `P0`
- Feature/flow: E2EE integrity and fallback safety across submission and notifications.
- Threat hypothesis: Encryption-failure paths leak plaintext disclosure content.
- Preconditions:
  - Recipient account with valid PGP key.
  - Exercise all notification modes: generic-only, include-content, encrypt-entire-body.
  - JS-enabled and JS-disabled clients.
- Steps:
  1. Submit messages through normal JS-enabled flow and inspect stored encrypted fields.
  2. Submit with missing/invalid `encrypted_email_body` to trigger fallback path.
  3. Submit with JS disabled to validate server-side encryption fallback behavior.
  4. Validate outbound email bodies for all notification modes.
  5. Verify behavior when encryption fails (forced exception path).
- Expected secure behavior: Encrypted data paths never degrade to unauthorized plaintext disclosure.
- Failure indicators: Plaintext sensitive message content in DB, response, or outbound notifications where encryption is expected.
- Evidence to collect:
  - DB samples of stored field values (redacted).
  - Mail sink captures for each mode.
  - Runtime logs showing fallback branch selection (without secret leakage).
- Suggested remediation owner: Crypto + Backend.

### HL-AUD-P0-005

- Test ID: `HL-AUD-P0-005`
- Priority: `P0`
- Feature/flow: SSRF protections in profile URL verification flow.
- Threat hypothesis: URL verification can be abused to reach internal or non-public network targets.
- Preconditions:
  - Controlled DNS and HTTP test infrastructure.
  - Production-like settings (`TESTING=false`).
- Steps:
  1. Test blocked targets: loopback, RFC1918, link-local, multicast, unspecified addresses.
  2. Test blocked hostnames: localhost variants and non-HTTPS URLs.
  3. Test redirect and DNS-rebinding variants from public host to private destination.
  4. Measure whether response/timing differences allow private-network enumeration.
- Expected secure behavior: Unsafe destinations are rejected pre-fetch; no internal network reachability.
- Failure indicators: Any successful fetch to private-network destination or distinguishable oracle behavior.
- Evidence to collect:
  - DNS and HTTP server logs proving attempted target resolution.
  - Application logs showing rejection reason categories.
  - Packet/network traces for disputed cases.
- Suggested remediation owner: Backend security owner.

### HL-AUD-P0-006

- Test ID: `HL-AUD-P0-006`
- Priority: `P0`
- Feature/flow: Outbound request hardening for SMTP host validation and Proton key lookup.
- Threat hypothesis: Outbound features can be redirected to unsafe hosts or abused for unexpected egress.
- Preconditions:
  - Authenticated user with notification settings access.
  - Controlled SMTP and DNS test hosts.
- Steps:
  1. Attempt custom SMTP server settings resolving to private/non-global IPs.
  2. Attempt hostname edge cases and resolution churn.
  3. Exercise Proton key lookup with malformed and high-volume inputs.
  4. Confirm egress target constraints and timeout/exception handling.
- Expected secure behavior: Only safe/expected outbound destinations accepted; failures are safe.
- Failure indicators: Connection to private hosts, uncontrolled redirects, or unbounded outbound attempts.
- Evidence to collect:
  - Config submissions and validation outcomes.
  - Outbound network captures.
  - Sanitized logs of blocked and allowed attempts.
- Suggested remediation owner: Backend security owner.

### HL-AUD-P0-007

- Test ID: `HL-AUD-P0-007`
- Priority: `P0`
- Feature/flow: Stripe payment integrity, webhook trust, replay/idempotency, and race handling.
- Threat hypothesis: Webhook/event processing can be forged, replayed, or raced into inconsistent tier state.
- Preconditions:
  - Premium-enabled deployment with Stripe test credentials.
  - Worker running for async event processing.
- Steps:
  1. Send invalid signature and malformed webhook payloads.
  2. Replay previously valid `event_id`s and verify idempotent handling.
  3. Submit out-of-order and concurrent duplicate subscription/invoice events.
  4. Validate resulting tier/subscription state transitions and invoice records.
  5. Exercise user actions (`upgrade`, `cancel`, `enable/disable-autorenew`) during webhook races.
- Expected secure behavior: Signature enforcement, replay resistance, idempotent processing, and deterministic account state.
- Failure indicators: Accepted forged webhooks, duplicate side effects, or inconsistent tier states.
- Evidence to collect:
  - Stripe event timeline with timestamps.
  - `stripe_events` and user tier DB snapshots.
  - Reproduction script for race scenario.
- Suggested remediation owner: Billing backend owner.

### HL-AUD-P0-008

- Test ID: `HL-AUD-P0-008`
- Priority: `P0`
- Feature/flow: Regression retest for `V-001 Blind SSRF private-network enumeration`.
- Threat hypothesis: Previously reported SSRF enumeration vector remains reachable.
- Current status assumption: Publicly unresolved in Subgraph report dated 2025-12-30; code indicates added SSRF guards but closure is unverified.
- Preconditions:
  - Public report baseline: unresolved in Subgraph 2025 report dated 2025-12-30.
  - Controlled internal-network canary endpoints.
- Steps:
  1. Re-run original finding class against URL verification and related outbound paths.
  2. Include DNS rebinding and redirect-to-private variants.
  3. Measure oracle conditions (timing/status/error-class leakage).
- Expected secure behavior: No direct/indirect private-network reachability or enumeration oracle.
- Failure indicators: Any reproducible private-network enumeration behavior.
- Evidence to collect:
  - Current-status conclusion: `closed` or `still open` with confidence.
  - Minimal reproducible script + logs + traffic trace.
  - Patch-verification notes if fixed.
- Suggested remediation owner: Backend security owner.

### HL-AUD-P0-009

- Test ID: `HL-AUD-P0-009`
- Priority: `P0`
- Feature/flow: Regression retest for `V-002 Client-side encryption timeout failure`.
- Threat hypothesis: Client encryption timeout/failure can cause unsafe plaintext behavior.
- Current status assumption: Publicly unresolved in Subgraph report dated 2025-12-30; code shows fallback handling but independent closure is unverified.
- Preconditions:
  - Public report baseline: unresolved in Subgraph 2025 report dated 2025-12-30.
  - Test profiles for notification modes and JS enabled/disabled.
- Steps:
  1. Force client-side encryption delay/failure on submission.
  2. Observe fallback behavior for storage, inbox render, and email forwarding.
  3. Verify no sensitive plaintext disclosure where encrypted behavior is required.
- Expected secure behavior: Safe server fallback or generic notification path without plaintext disclosure.
- Failure indicators: Plaintext leakage due to client-side timeout/failure.
- Evidence to collect:
  - Storage and notification artifact review (redacted).
  - Failure-path request/response traces.
  - Closure statement tied to observed fallback path.
- Suggested remediation owner: Crypto + Backend.

### HL-AUD-P0-010

- Test ID: `HL-AUD-P0-010`
- Priority: `P0`
- Feature/flow: Regression retest for `V-003 Sequential message IDs`.
- Threat hypothesis: Message identifiers are still guessable/sequential enough for enumeration.
- Current status assumption: Publicly unresolved in Subgraph report dated 2025-12-30; current model appears UUID-based but closure is unverified.
- Preconditions:
  - Public report baseline: unresolved in Subgraph 2025 report dated 2025-12-30.
  - High-volume message creation dataset.
- Steps:
  1. Generate a large sample of message identifiers across accounts.
  2. Assess predictability and adjacency patterns for externally exposed IDs.
  3. Attempt unauthorized retrieval using guessed identifier space.
- Expected secure behavior: Public identifiers are non-sequential and non-guessable in practice.
- Failure indicators: Predictable identifier progression enabling practical enumeration.
- Evidence to collect:
  - Entropy/predictability analysis.
  - Guess-attempt success/failure logs.
  - Clear closure recommendation.
- Suggested remediation owner: Backend data model owner.

### HL-AUD-P1-011

- Test ID: `HL-AUD-P1-011`
- Priority: `P1`
- Feature/flow: Sensitive data logging and telemetry hygiene.
- Threat hypothesis: Error/debug paths leak disclosures, keys, or secrets to logs.
- Preconditions:
  - Centralized log capture enabled for app and worker.
  - Triggerable error paths (SMTP failure, encryption error, webhook failure).
- Steps:
  1. Trigger controlled failures across submission, encryption, notification, and webhook paths.
  2. Inspect application and worker logs for plaintext message content, PGP key material, SMTP creds, tokens.
  3. Check metadata minimization in logs and error bodies.
- Expected secure behavior: Sensitive values absent/redacted; operational context retained.
- Failure indicators: Disclosures, keys, credentials, or unnecessary identifying metadata in logs.
- Evidence to collect:
  - Redacted log excerpts by test path.
  - Log-field inventory and sensitivity classification.
- Suggested remediation owner: Backend + SRE.

### HL-AUD-P1-012

- Test ID: `HL-AUD-P1-012`
- Priority: `P1`
- Feature/flow: Session security and 2FA robustness.
- Threat hypothesis: Session fixation/replay or 2FA edge cases permit account takeover.
- Preconditions:
  - Accounts with and without 2FA enabled.
  - Browser tooling for cookie/session replay.
- Steps:
  1. Test session fixation across login transitions.
  2. Test replay of stale session artifacts after logout.
  3. Validate 2FA replay prevention within same TOTP time window.
  4. Validate failed-attempt throttling and error-path consistency.
  5. Confirm logout sets `Clear-Site-Data` and effective client cleanup.
- Expected secure behavior: Session and 2FA transitions resist replay/fixation.
- Failure indicators: Reusable session IDs, bypassable 2FA guardrails, or stale authenticated state after logout.
- Evidence to collect:
  - Cookie/session timeline.
  - Auth log and rate-limit behavior traces.
- Suggested remediation owner: Auth backend owner.

### HL-AUD-P1-013

- Test ID: `HL-AUD-P1-013`
- Priority: `P1`
- Feature/flow: Privacy rights, export/delete lifecycle, and tenancy boundaries.
- Threat hypothesis: Export/delete flows leak other-tenant data or leave sensitive residuals.
- Preconditions:
  - Multi-user dataset with messages, aliases, auth logs, and status texts.
- Steps:
  1. Validate exported bundle contains only current user tenant data.
  2. Validate encrypted export mode and failure handling.
  3. Execute self-delete and admin-delete flows.
  4. Confirm related records and dependent artifacts are removed.
- Expected secure behavior: Tenant-isolated export and complete scoped deletion.
- Failure indicators: Cross-tenant data in export or orphaned sensitive records after delete.
- Evidence to collect:
  - Export contents diff by user.
  - Post-delete DB integrity checks.
- Suggested remediation owner: Backend data owner.

### HL-AUD-P1-014

- Test ID: `HL-AUD-P1-014`
- Priority: `P1`
- Feature/flow: Receiver authenticity and verification trust signals.
- Threat hypothesis: Verification/admin trust indicators can be spoofed or confused by user content.
- Preconditions:
  - Verified and unverified profiles.
  - Directory and profile pages with configurable display/bio/header content.
- Steps:
  1. Attempt visual spoofing of verified/admin trust markers via profile fields and custom templates.
  2. Compare trust cues in directory cards, verified tab, and profile pages.
  3. Validate consistency between API flags and UI badges.
- Expected secure behavior: Trust indicators are unambiguous and controlled by authoritative state.
- Failure indicators: User-controlled content mimics authoritative verification signals.
- Evidence to collect:
  - UI screenshots by role/state.
  - Mismatch table (state vs rendered trust cues).
- Suggested remediation owner: Product + Frontend + Backend.

### HL-AUD-P1-015

- Test ID: `HL-AUD-P1-015`
- Priority: `P1`
- Feature/flow: Abuse resistance and rate controls.
- Threat hypothesis: Brute force, enumeration, or submission flood is insufficiently controlled.
- Preconditions:
  - Automated test client with tunable request rates.
- Steps:
  1. Attempt username/password brute-force and account enumeration through login/register responses.
  2. Attempt 2FA brute-force and replay across timing boundaries.
  3. Attempt message submission flood and CAPTCHA bypass patterns.
  4. Evaluate consistency of error messaging to prevent account discovery.
- Expected secure behavior: Effective throttling/friction without sensitive enumeration leakage.
- Failure indicators: Unlimited attempts, obvious enumeration or flood success.
- Evidence to collect:
  - Rate-limit threshold measurements.
  - Request/response and status-distribution data.
- Suggested remediation owner: Backend security owner.

### HL-AUD-P1-016

- Test ID: `HL-AUD-P1-016`
- Priority: `P1`
- Feature/flow: File and object storage handling (branding/logo and public asset serving).
- Threat hypothesis: Upload/serving controls allow unsafe content or path abuse.
- Preconditions:
  - Admin account for branding upload.
  - File-system and S3 storage drivers tested separately.
- Steps:
  1. Attempt invalid file types, oversized files, and malformed PNG/polyglot samples.
  2. Attempt path traversal/device-name path edge cases on asset serving paths.
  3. Validate object ACL behavior and public/private storage assumptions.
- Expected secure behavior: Strict type/size/path controls and correct access boundaries.
- Failure indicators: Unsafe file acceptance, path breakout, or unintended object exposure.
- Evidence to collect:
  - Upload attempt matrix and outcomes.
  - Storage backend access logs and object metadata.
- Suggested remediation owner: Backend + Platform.

### HL-AUD-P1-017

- Test ID: `HL-AUD-P1-017`
- Priority: `P1`
- Feature/flow: Browser residual risk (service worker/cache/localStorage).
- Threat hypothesis: Shared-device sessions can leak sensitive data post-logout.
- Preconditions:
  - Real browser profile with DevTools access.
  - Authenticated session including inbox/message views.
- Steps:
  1. Navigate authenticated sensitive pages, then logout.
  2. Inspect service worker cache entries, localStorage, and offline behavior.
  3. Attempt back-button/offline retrieval of sensitive content.
- Expected secure behavior: No sensitive message/account data recoverable after logout.
- Failure indicators: Cached sensitive pages/data accessible after logout.
- Evidence to collect:
  - Cache storage dump and localStorage keys.
  - Replay attempts with network offline/online.
- Suggested remediation owner: Frontend owner.

### HL-AUD-P1-018

- Test ID: `HL-AUD-P1-018`
- Priority: `P1`
- Feature/flow: Admin mutation integrity across branding/guidance/registration/verification/user management.
- Threat hypothesis: Admin control-plane mutations can be reached or abused by non-admins or stale/broken auth context.
- Preconditions:
  - Admin and non-admin accounts.
  - Registration settings enabled.
- Steps:
  1. Attempt each admin mutation route as non-admin.
  2. Attempt same with expired/stale session states.
  3. Validate successful admin changes for expected scope only.
  4. Confirm no hidden side effects outside targeted setting.
- Expected secure behavior: Admin-only enforcement and narrowly scoped mutations.
- Failure indicators: Non-admin mutation success or unintended side effects.
- Evidence to collect:
  - Route-by-route authorization matrix.
  - Before/after setting state snapshots.
- Suggested remediation owner: Backend admin owner.

### HL-AUD-P2-019

- Test ID: `HL-AUD-P2-019`
- Priority: `P2`
- Feature/flow: Tools attack surface (`/email-headers`, evidence ZIP/PDF generation, Vision tool access path).
- Threat hypothesis: Tooling features permit parser abuse, resource exhaustion, or unsafe artifact generation.
- Preconditions:
  - Authenticated user account.
  - Corpus of malformed and large header samples.
- Steps:
  1. Fuzz raw header parser with malformed/oversized inputs.
  2. Stress evidence ZIP/PDF generation for resource and injection safety.
  3. Validate auth boundaries for tools pages and exports.
  4. For Vision path, validate current access controls and future upload assumptions.
- Expected secure behavior: Bounded resource use and safe artifact generation.
- Failure indicators: Crashes, timeouts, excessive memory/CPU, or unsafe artifact content interpretation.
- Evidence to collect:
  - Performance/resource profiles.
  - Crash traces and minimal reproductions.
- Suggested remediation owner: Tools backend owner.

### HL-AUD-P2-020

- Test ID: `HL-AUD-P2-020`
- Priority: `P2`
- Feature/flow: Supply chain and workflow security.
- Threat hypothesis: Dependency/workflow hardening assumptions are incomplete, creating CI/CD compromise risk.
- Preconditions:
  - Access to workflow definitions and dependency manifests.
- Steps:
  1. Validate action pinning strategy and mutable-tag usage risk.
  2. Validate interpolation guardrails for untrusted GitHub event text.
  3. Validate dependency-audit workflow coverage for runtime/build/dev contexts.
  4. Validate branch-protection required checks alignment with security policy.
- Expected secure behavior: CI workflows enforce documented supply-chain controls.
- Failure indicators: Unsafe interpolation paths, unreviewed mutable actions, or missing required security checks.
- Evidence to collect:
  - Workflow control checklist.
  - Gaps with risk rating and concrete hardening recommendations.
- Suggested remediation owner: DevSecOps/Platform.

## 2) Core-Flow Coverage Matrix (AGENTS.md)

| Core flow group            | Core flow                                     | Mapped audit tests                                |
| -------------------------- | --------------------------------------------- | ------------------------------------------------- |
| Unauthenticated users      | Send a message                                | `HL-AUD-P0-004`, `HL-AUD-P1-015`                  |
| Unauthenticated users      | Register/login, 2FA challenge                 | `HL-AUD-P1-012`, `HL-AUD-P1-015`                  |
| Unauthenticated users      | Browse user directory                         | `HL-AUD-P0-002`, `HL-AUD-P1-014`                  |
| Unauthenticated users      | Search Verified tab                           | `HL-AUD-P0-002`                                   |
| Unauthenticated users      | Search All tab                                | `HL-AUD-P0-002`                                   |
| Unauthenticated users      | E2EE defaults and behavior                    | `HL-AUD-P0-004`, `HL-AUD-P0-009`                  |
| Authenticated, all users   | Send a message                                | `HL-AUD-P0-004`                                   |
| Authenticated, all users   | View messages in Inbox                        | `HL-AUD-P0-003`                                   |
| Authenticated, all users   | Change message status                         | `HL-AUD-P0-001`, `HL-AUD-P0-003`                  |
| Authenticated, all users   | Delete a message                              | `HL-AUD-P0-001`, `HL-AUD-P0-003`                  |
| Authenticated, all users   | Resend message to email (if enabled)          | `HL-AUD-P0-003`, `HL-AUD-P0-004`                  |
| Authenticated, all users   | Upgrade to Super User                         | `HL-AUD-P0-001`, `HL-AUD-P0-007`                  |
| Authenticated, all users   | Add PGP key via Proton Key Lookup             | `HL-AUD-P0-006`                                   |
| Authenticated, all users   | Add PGP key manually                          | `HL-AUD-P0-004`, `HL-AUD-P1-011`                  |
| Authenticated, all users   | Add display name                              | `HL-AUD-P0-002`, `HL-AUD-P1-014`                  |
| Authenticated, all users   | Add bio                                       | `HL-AUD-P0-002`, `HL-AUD-P1-014`                  |
| Authenticated, all users   | Add additional profile fields                 | `HL-AUD-P0-005`, `HL-AUD-P1-014`                  |
| Authenticated, all users   | Opt in to user directory                      | `HL-AUD-P1-014`                                   |
| Authenticated, all users   | Change username/password                      | `HL-AUD-P1-012`, `HL-AUD-P1-015`                  |
| Authenticated, all users   | Enable/disable 2FA                            | `HL-AUD-P0-001`, `HL-AUD-P1-012`                  |
| Authenticated, all users   | Download account data                         | `HL-AUD-P1-013`                                   |
| Authenticated, all users   | Delete own user account                       | `HL-AUD-P0-001`, `HL-AUD-P1-013`                  |
| Authenticated, all users   | Validate Raw Email Headers                    | `HL-AUD-P2-019`                                   |
| Authenticated, all users   | Add an image to Vision for OCR                | `HL-AUD-P2-019`                                   |
| Authenticated, all users   | View Tools tab in nav                         | `HL-AUD-P2-019`                                   |
| Authenticated, paid users  | Cancel subscription                           | `HL-AUD-P0-001`, `HL-AUD-P0-007`                  |
| Authenticated, paid users  | Resubscribe to Super User tier                | `HL-AUD-P0-001`, `HL-AUD-P0-007`                  |
| Authenticated, paid users  | Add/remove an Alias                           | `HL-AUD-P0-001`, `HL-AUD-P0-003`                  |
| Authenticated, paid users  | Add/remove custom profile fields              | `HL-AUD-P0-003`, `HL-AUD-P0-005`                  |
| Authenticated, admin users | Update directory intro text                   | `HL-AUD-P0-001`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Change primary color                          | `HL-AUD-P0-001`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Change app name                               | `HL-AUD-P0-001`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Upload new logo                               | `HL-AUD-P0-001`, `HL-AUD-P1-016`, `HL-AUD-P1-018` |
| Authenticated, admin users | Hide donation link                            | `HL-AUD-P0-001`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Customize profile header                      | `HL-AUD-P1-014`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Change homepage; Enable/disable User Guidance | `HL-AUD-P1-017`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Update Emergency Exit link                    | `HL-AUD-P1-018`                                   |
| Authenticated, admin users | Update prompt heading/body                    | `HL-AUD-P1-018`                                   |
| Authenticated, admin users | Add new prompt                                | `HL-AUD-P1-018`                                   |
| Authenticated, admin users | Enable/disable new registrations              | `HL-AUD-P1-015`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Enable/disable registration code gating       | `HL-AUD-P1-015`, `HL-AUD-P1-018`                  |
| Authenticated, admin users | Make user account admin                       | `HL-AUD-P0-001`, `HL-AUD-P0-003`, `HL-AUD-P1-018` |
| Authenticated, admin users | Verify a primary user account                 | `HL-AUD-P0-001`, `HL-AUD-P1-014`, `HL-AUD-P1-018` |
| Authenticated, admin users | Verify an alias user account                  | `HL-AUD-P0-001`, `HL-AUD-P1-014`, `HL-AUD-P1-018` |
| Authenticated, admin users | Delete a user account                         | `HL-AUD-P0-001`, `HL-AUD-P0-003`, `HL-AUD-P1-013` |

## 3) Required Codebase-Specific Target Coverage Check

| Required target                              | Covered by                                        |
| -------------------------------------------- | ------------------------------------------------- |
| CSRF on state-changing routes                | `HL-AUD-P0-001`                                   |
| Stored/DOM XSS in directory/search rendering | `HL-AUD-P0-002`                                   |
| AuthN/AuthZ boundary checks                  | `HL-AUD-P0-003`                                   |
| E2EE integrity and fallback safety           | `HL-AUD-P0-004`                                   |
| SSRF and outbound request hardening          | `HL-AUD-P0-005`, `HL-AUD-P0-006`, `HL-AUD-P0-008` |
| Payment integrity and webhook trust          | `HL-AUD-P0-007`                                   |
| Sensitive data logging and telemetry         | `HL-AUD-P1-011`                                   |
| Session and 2FA robustness                   | `HL-AUD-P1-012`                                   |
| Privacy rights and data lifecycle            | `HL-AUD-P1-013`                                   |
| Receiver authenticity / verification trust   | `HL-AUD-P1-014`                                   |
| Abuse resistance / rate controls             | `HL-AUD-P1-015`                                   |
| File and object storage handling             | `HL-AUD-P1-016`                                   |
| Browser residual risk                        | `HL-AUD-P1-017`                                   |
| Tools attack surface                         | `HL-AUD-P2-019`                                   |
| Supply chain and workflow security           | `HL-AUD-P2-020`                                   |

## 4) Engagement Brief for External Firm

### Environment requirements

- Test environments only: local/staging; no destructive production testing.
- Execute both app profiles:
  - Managed-service parity profile: `STRIPE_SECRET_KEY` set, `USER_VERIFICATION_ENABLED=true`, branding/admin features enabled.
  - Self-hosted parity profile: premium disabled (`STRIPE_SECRET_KEY` absent), feature flags representative of personal-server defaults.
- Execute both client profiles for submission flows:
  - JS-enabled browser path.
  - JS-disabled fallback path.
- Execute both deployment variants where behavior differs:
  - Premium-enabled and premium-disabled.
  - File-system and S3 public storage drivers for branding/assets.

### Rules of engagement

- Treat whistleblower-message flows as safety-critical.
- Use only synthetic test data; never process real disclosures in audit exercises.
- Keep exploit specifics in private report channels only.
- If a high-confidence vulnerability is found, use coordinated private disclosure per [`SECURITY.md`](../SECURITY.md) before any public detail.

### Required evidence format (per finding and per passed critical test)

- Test metadata: `Test ID`, environment profile, commit SHA, date/time UTC, tester.
- Repro narrative: exact preconditions and step sequence.
- Technical artifacts:
  - HTTP request/response captures.
  - Browser/DOM evidence for client-side issues.
  - DB before/after state snapshots (redacted).
  - Relevant logs (redacted for secrets/disclosure content).
  - For network issues: DNS and packet traces when applicable.
- Assessment output:
  - Severity rating and exploitability.
  - Affected data path(s) and impacted core flow(s).
  - Recommended fix and verification retest.
  - Confidence level and limitations.

## 5) Human-Assessment Gap List (where automation is insufficient)

1. Comprehensive CSRF assurance across all mutation routes is not covered end-to-end in default tests because test config commonly runs with `WTF_CSRF_ENABLED=false`.
2. Directory/client-side search rendering lacks adversarial browser validation for DOM XSS in dynamic `innerHTML` paths.
3. SSRF testing in automation primarily validates deterministic allow/deny logic; it does not fully cover rebinding, redirect chains, and side-channel enumeration behavior.
4. Stripe webhook race and concurrency behavior is partially unit-tested, but requires live adversarial timing tests for idempotency under load.
5. Logging hygiene is not comprehensively validated for absence of secrets/disclosure content across all exception and fallback paths.
6. Session fixation/replay resilience is only partially covered; full browser-level token lifecycle validation is needed.
7. Abuse-resistance controls (brute force, enumeration, and submission flood) require sustained-rate and distributed-source testing beyond current functional tests.
8. Browser residual risks (service-worker cache, localStorage persistence, shared-device recovery) are not validated by automated integration tests.
9. File upload hardening needs adversarial content-type/polyglot verification across both storage backends.
10. Workflow/supply-chain controls need periodic human review for mutable action refs, policy drift, and branch-protection alignment.

## 6) Redacted Disclosure Note

- Redacted note `HL-SEC-2026-02-24-R1`: Prep identified a plausible client-side injection risk class in directory search rendering paths. Reproduction details are intentionally omitted from this document. Handle through private disclosure workflow per [`SECURITY.md`](../SECURITY.md).
