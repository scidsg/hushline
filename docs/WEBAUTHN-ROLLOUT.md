# Security-key rollout and release record

This runbook controls the additive WebAuthn launch. It is also the release-evidence record that
must be completed at the exact candidate commit. Empty or `Pending` fields are release blockers,
not evidence of a successful test. Do not record usernames, email addresses, IP addresses,
credential IDs, public keys, challenges, cookies, recovery codes, or disclosure data here or in
linked artifacts.

Production deployment and final merge require explicit approval from the named release owner and
security reviewer. Preparing or approving a pull request does not itself authorize either action.

## Release record

- Candidate commit: Pending
- Release/version: Pending
- Integration PR to `main`: Pending; keep draft until every gate below passes
- Release owner: Pending named human
- Security reviewer: Pending named human
- Deployment operator: Pending named human
- Incident/rollback owner: Pending named human
- Human merge approval: Pending
- Human production-launch approval: Pending
- Schema deployment identifier and time: Pending
- Enrollment cohort: Pending; sanitized count and approval link only
- Production launch time: Pending

The final PR must be conflict-free with `main`, contain signed and remotely verifiable commits,
and accurately describe the final scope. Record passing required checks, dependency audits,
focused authentication tests, full tests and coverage, CSP regressions, and the
`WebAuthn Integrated Validation` artifact at the exact candidate commit. Resolve security review
and all actionable human or Codex review threads before requesting merge.

## Configuration and trust scope

Set both trust roots explicitly:

- `WEBAUTHN_RP_ID` is the exact hostname, or a deliberately reviewed registrable parent. It has
  no scheme or port.
- `WEBAUTHN_ORIGIN` is the one exact public origin, including scheme and any non-default port.
- `WEBAUTHN_RP_NAME` is the name shown by the browser; it defaults to `Hush Line`.
- `WEBAUTHN_ENROLLMENT_ENABLED` defaults to `false`.
- `WEBAUTHN_ENROLLMENT_USER_IDS` is empty for nobody, a comma-separated list of positive database
  user IDs for an approved cohort, or `*` for an approved all-user launch.

Do not infer trust roots from request or proxy headers. Do not put usernames or other direct
identifiers in rollout configuration. An HTTPS hostname and an onion hostname are distinct
WebAuthn trust scopes. Changing either trust root after enrollment can strand credentials; stop
and conduct a migration/security review instead.

Enrollment is available only when its switch is true and the account is in the configured
population. Authentication, recovery, rename, and removal of existing credentials do not consult
the enrollment switch. If trust-root configuration becomes invalid, ceremonies fail closed; the
application must never treat the affected account as password-only.

## Rollout sequence

1. Deploy the additive WebAuthn and recovery-code schema with enrollment disabled and the
   population empty. Confirm migration compatibility and that password-only and TOTP accounts
   retain their existing behavior before changing enrollment configuration.
2. In ephemeral staging, use synthetic accounts only. Complete every row in the staging table
   and the applicable physical-device rows in
   [the integrated validation protocol](WEBAUTHN-VALIDATION.md). Record the exact deployed commit,
   RP ID, origin, browser versions, and sanitized evidence links.
3. Drill the kill switch in staging: begin an enrollment, set
   `WEBAUTHN_ENROLLMENT_ENABLED=false`, apply the normal configuration deployment, and confirm the
   pending verification is rejected without storing a credential. Confirm that a previously
   enrolled primary and backup key still authenticate and recover the account.
4. After the release owner and security reviewer approve the recorded staging evidence, enable
   only the production synthetic account IDs. Complete the production synthetic matrix and switch
   enrollment off again while results are reviewed.
5. Enable only the approved real-user cohort IDs. Observe the aggregate metrics and stop
   thresholds for the approved observation window. Expanding the list is a new rollout decision.
6. Set the population to `*` only after explicit all-user approval. Keep the enrollment switch
   independent so it remains an immediate, enrollment-only kill switch.

### Staging synthetic matrix

- Password only: login; password change; generic password-reset request; confirm no
  security-key prompt. Result/evidence: Pending.
- Password + TOTP: login; single-use TOTP enforcement; add and remove a key without removing
  TOTP; recovery code. Result/evidence: Pending.
- Password + primary and backup keys: login with each key; revoke primary; reject revoked key;
  recover with backup; replace key. Result/evidence: Pending.
- Password + key + recovery codes: consume one code once; reject replay; rotate codes; confirm
  account access does not unlock old encrypted chat history. Result/evidence: Pending.

Repeat the key cases at the canonical public origin through the configured proxy. Complete the
dedicated onion-origin case separately when that deployment is in launch scope. A virtual
authenticator does not satisfy physical USB or NFC evidence.

### Production synthetic record

- [ ] Enrollment switch initially disabled and population empty — evidence: Pending
- [ ] Password-only login remains unchanged — evidence: Pending
- [ ] TOTP login and replay rejection remain unchanged — evidence: Pending
- [ ] Primary physical-key enrollment and login — evidence: Pending
- [ ] Separately stored backup-key enrollment and login — evidence: Pending
- [ ] Primary revocation and rejected reuse — evidence: Pending
- [ ] Backup-key recovery and replacement enrollment — evidence: Pending
- [ ] Recovery-code single use and replay rejection — evidence: Pending
- [ ] Kill-switch drill preserves enrolled-key login — evidence: Pending
- [ ] Synthetic accounts and test artifacts cleaned up — evidence: Pending

## Stop thresholds and health observations

The following are immediate stop and rollback conditions with zero tolerance:

- any authentication bypass, cross-account credential acceptance, origin/RP mismatch, replay,
  or silent password-only downgrade;
- any enrolled account that cannot use a known-good primary key, backup key, TOTP factor, or
  unused recovery code according to its configured policy;
- any regression in session rotation, password reset, TOTP replay prevention, CSP, E2EE, or
  encrypted conversation access;
- any log, metric, screenshot, or artifact containing prohibited authentication or disclosure
  material.

Before launch, the release owner must also record deployment-specific numeric stop thresholds and
their observation window for enrollment 4xx/5xx rates, authentication 4xx/5xx rates, and support
reports. Those values must be based on reviewed staging/baseline data; do not invent them here.

- Enrollment endpoint error rate — threshold/window: Pending; result: Pending; owner: Pending
- Enrolled-key authentication error rate — threshold/window: Pending; result: Pending; owner:
  Pending
- Recovery failure reports — threshold/window: Pending; result: Pending; owner: Pending
- Security-key users / active keys — threshold/window: Pending; result: Pending; owner: Pending

Use the admin Metrics page for aggregate security-key user and active-key counts. At the service
edge, retain only aggregate status counts needed for the approved window. Do not add credential
material, key labels, usernames, request bodies, query strings, IP addresses, or per-user ceremony
traces to release evidence.

## Rollback and kill-switch drill

For enrollment-specific failures, set `WEBAUTHN_ENROLLMENT_ENABLED=false` and apply the normal
configuration deployment. Leave the RP ID, origin, schema, credential readers, login routes, and
recovery routes intact. Verify all of the following before declaring the rollback stable:

- settings clearly report that new enrollment is paused and expose no enrollment form;
- both enrollment endpoints return `503` with `Cache-Control: no-store`;
- no credential is stored from a ceremony that was pending when the switch changed;
- enrolled primary and backup keys still authenticate;
- key removal, TOTP, and recovery codes retain their reviewed behavior;
- password-only accounts are unchanged, and no protected account is silently converted to
  password-only.

If enrolled-key authentication itself is unsafe, stop the rollout and fail closed. Roll back to a
reviewed application release that can read the additive schema; do not disable key requirements,
delete credentials, clear the RP configuration, or remove schema as an emergency shortcut.

## Completion gate

Do not mark the launch complete until every `Pending` release, owner, approval, staging,
production-synthetic, health, and evidence field above has a truthful value; the approved
production population can enroll and authenticate with physical keys; recovery and rollback have
been drilled; and the final PR has been explicitly approved for merge and release by humans.
