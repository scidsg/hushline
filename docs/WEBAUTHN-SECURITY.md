# WebAuthn verifier and privacy review

Hush Line pins `webauthn` 3.0.1 (Duo Labs `py_webauthn`) for server-side WebAuthn parsing and verification. The project is production-stable, supports Python 3.10 and later, publishes source, and uses the BSD-3-Clause license, which is compatible with Hush Line's AGPL-3.0 distribution. The pinned release fixes rejection of malformed attestation format values.

Its direct verification dependencies resolve in `poetry.lock` to `cbor2` 6.1.2 (MIT), `cryptography` 50.0.0 (Apache-2.0 or BSD-3-Clause), `pyasn1` 0.6.2 (BSD-2-Clause), `pyasn1-modules` 0.4.2 (BSD-2-Clause), and `pyOpenSSL` 26.4.0 (Apache-2.0). Those licenses are compatible with distribution of Hush Line. `pyOpenSSL` 26.4.0 is used because its declared range includes the existing `cryptography` 50 dependency. All of these packages remain subject to the repository dependency-audit workflow.

The integration supplies an exact configured origin and RP ID to every verification call. Configuration fails closed when either value is absent or invalid, and request host or proxy headers are not trust inputs. Registration and authentication require user presence and user verification. Challenges are random, short-lived, account-, purpose-, and session-bound, stored only as hashes, rate limited, and atomically consumed before response verification.

Registration requests `none` attestation. Hush Line does not retain attestation objects, AAGUIDs, certificates, or other authenticator-vendor identifiers. A security key proves control of a credential private key and the configured user-verification ceremony; it does not prove a person's civil identity, employment, device ownership, or that one physical authenticator is permanently unique. Synced credentials may be reported as multi-device and backed up, so they must not be represented as hardware-bound.

Credential IDs and public keys are authentication material, not disclosure content, but they are excluded from account data exports and must not be logged. Verifier exceptions are converted to generic service errors so malformed credential data and public keys do not enter application logs.

Security-key inventory and pending MFA pages are served with `Cache-Control: no-store` so browser and intermediary caches do not retain key labels, last-used timestamps, or the account's enabled factor choices.

Removing a credential disables it under the account policy lock, consumes outstanding WebAuthn challenges, rotates the account session identifier, and prunes revoked credential records against configured age and count bounds during factor-policy changes. Concurrent assertions either finish before revocation and are invalidated by session rotation, or fail against the disabled credential. Ordinary removal cannot remove the last primary factor; disabling every factor is a separate, acknowledged action after password-plus-factor reauthentication and also invalidates recovery codes.

TOTP codes remain single-use within their time step across mixed-factor activity. Replay detection checks the exact successful TOTP use under the account policy lock, so a later security-key or recovery-code success cannot hide the used code and concurrent submissions cannot both pass.

Physical-device, browser, adversarial, proxy, onion, accessibility, and performance evidence follows
the [WebAuthn integrated validation protocol](WEBAUTHN-VALIDATION.md).

## Integration interfaces

Enrollment callers use `WebAuthnCeremonyService.begin_registration()` and `finish_registration()`. Login callers use `begin_authentication()` and `finish_authentication()` with the default `authentication` purpose; reviewed recovery flows use the same pair with `WebAuthnPurpose.RECOVERY`. Callers obtain the binding from `current_webauthn_session_binding()` and must not supply a request host as ceremony configuration. The begin methods return JSON-ready browser options, and the finish methods return the persisted, account-owned credential only after successful verification.
