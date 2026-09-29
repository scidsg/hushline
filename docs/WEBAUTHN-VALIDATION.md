# WebAuthn integrated validation

This is the evidence protocol for security-key changes. A ticket is not complete until every
applicable automated run and physical-device row is attached to the review at an exact commit.
Virtual-authenticator results never substitute for physical USB or NFC results.

Do not record credential IDs, public keys, private keys, challenges, cookies, CSRF tokens,
recovery codes, account exports, or disclosure data. Use only seeded synthetic accounts.

## Automated evidence

The `WebAuthn Integrated Validation` workflow checks out the candidate commit and publishes these
results:

- `make lint` and full `make test` behavior-critical coverage, including authentication, settings,
  recovery, security headers, and E2EE regressions.
- Python, Node runtime, and full Node dependency audits.
- A real Chromium CDP virtual-authenticator ceremony against the integrated application. It uses
  two distinct CTAP 2.1 authenticators to enroll primary and backup credentials, log in, revoke the
  primary credential, recover with the backup, and clean up the synthetic account.
- Two sanitized screenshots and JSON metadata containing the commit, browser version, configured
  RP/origin, virtual transports, completed scenarios, and excluded sensitive fields.

The workflow artifact is named `webauthn-browser-evidence` and is retained for 14 days. Link the
successful workflow run in the PR and copy durable, sanitized release evidence to the approved
release-evidence location before merge.

The repository's separate required checks remain authoritative. Accessibility must score 100 and
performance must score at least 95. A workflow artifact or unchecked table is not a pass.

## Adversarial regression map

| Risk                                  | Executable coverage                                                                                 |
| ------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Cross-account credential use          | `test_authentication_rejects_a_credential_owned_by_another_account`                                 |
| Origin or RP substitution             | `test_registration_rejects_wrong_origin_or_rp`                                                      |
| Host or proxy-header poisoning        | `test_configured_rp_is_not_replaced_by_proxy_or_request_headers`                                    |
| Challenge replay or purpose confusion | `test_challenge_is_bound_to_account_purpose_session_and_single_use`                                 |
| Session-change bypass                 | `test_auth_session_rotation_invalidates_challenge_binding` and security-key login concurrency tests |
| Concurrent assertion or revocation    | `test_counter_update_rejects_concurrent_use_but_allows_zero_counters` and removal/revocation tests  |
| Counter rollback                      | `test_zero_counter_authenticator_is_allowed_and_counter_replay_is_rejected`                         |
| Factor-change bypass                  | settings security-key and 2FA policy tests                                                          |
| Password-reset or recovery downgrade  | recovery-code and security-key login tests                                                          |
| CSRF                                  | `test_security_key_json_routes_require_csrf` and login CSRF tests                                   |
| CSP broadening                        | security-key cases in `tests/test_security_headers.py`                                              |

## Deployment trust-boundary checks

Record the deployed values and result without secrets. `WEBAUTHN_RP_ID` must be the exact RP
hostname or a deliberate registrable parent, and `WEBAUTHN_ORIGIN` must be the one exact public
origin. Neither value may come from `Host`, `Forwarded`, or `X-Forwarded-*` request headers.

| Deployment              | RP ID                              | Origin                         | Proxy/public-host result                    | Status     |
| ----------------------- | ---------------------------------- | ------------------------------ | ------------------------------------------- | ---------- |
| Local integrated build  | `localhost`                        | `http://localhost:8080`        | Automated virtual ceremony                  | CI pending |
| Ephemeral staging       | Record unique staging hostname     | Record exact HTTPS origin      | Test direct and through configured proxy    | Pending    |
| Self-hosted HTTPS       | Record configured hostname         | Record exact HTTPS origin      | Test canonical and hostile forwarded hosts  | Pending    |
| Dedicated onion service | Record 56-character onion hostname | Record exact HTTP onion origin | Test through Tor, not a clearnet substitute | Pending    |

An HTTPS hostname and an onion hostname are different WebAuthn trust scopes. Test a dedicated onion
configuration with credentials enrolled on that onion origin; do not weaken origin checking to make
a clearnet credential work on an onion origin. Record an unsupported browser/authenticator pairing
as `Unsupported`, with the observed browser message, rather than changing RP validation.

## Physical-key browser and device matrix

Use two physically separate YubiKeys; record any non-YubiKey compatibility cases separately. For
each row, perform primary enrollment and login, backup enrollment and login, primary revocation,
rejected use of the revoked primary, recovery with the backup, recovery-code login, and cleanup.
Exercise USB and NFC where the listed device supports them. Record `Pass`, `Fail`, or `Unsupported`;
never infer a result from a virtual authenticator.

| OS/device           | Browser        | Key model               | Firmware | Transport     | Result  | Evidence/notes                        |
| ------------------- | -------------- | ----------------------- | -------- | ------------- | ------- | ------------------------------------- |
| Linux desktop       | Chrome         | Pending hardware access | Pending  | USB           | Pending | Required physical run                 |
| Linux desktop       | Firefox        | Pending hardware access | Pending  | USB           | Pending | Required physical run                 |
| Windows desktop     | Edge           | Pending hardware access | Pending  | USB           | Pending | Required physical run                 |
| macOS desktop       | Safari         | Pending hardware access | Pending  | USB           | Pending | Required physical run                 |
| Android device      | Chrome         | Pending hardware access | Pending  | NFC and USB-C | Pending | Required physical run                 |
| iOS device          | Safari         | Pending hardware access | Pending  | NFC           | Pending | Required physical run                 |
| Tor Browser desktop | Record version | Pending hardware access | Pending  | USB           | Pending | Use the dedicated onion configuration |

For every execution, also record:

- Candidate commit SHA and deployment identifier.
- OS/device model and version, browser name and full version, key model and firmware, and transport.
- Whether user presence and user verification were requested and observed.
- Pass/fail/unsupported for every scenario, with sanitized screenshots or logs for failures.
- Accessibility and performance scores where the repository checks apply.
- Remediation commit and complete rerun links for any failure.

The physical matrix, staging/proxy checks, and Tor/onion run remain explicit reviewer validation
tasks until real devices and those environments are available. They must not be marked complete
from mocked, unit, or virtual-authenticator evidence.
