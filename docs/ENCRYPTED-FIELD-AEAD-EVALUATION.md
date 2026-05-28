# Encrypted Field AEAD Evaluation

Date: 2026-05-26

Status: AES-GCM production writer implemented for new encrypted-field writes

## Scope

This memo evaluates the choice to support AES-GCM encrypted database-field
writes after Hush Line has already introduced versioned envelopes, stable
domains, associated data, dual-read rollout controls, and a tested migration
runbook.

It does not change default production encryption behavior. Production writes
remain controlled by `ENCRYPTED_FIELD_WRITE_FORMAT`, whose default is legacy
Fernet. `ENCRYPTED_FIELD_WRITE_FORMAT=envelope-aes-gcm` promotes the AES-GCM
helper in `hushline.crypto` to a production write path for new values.

Maintainers decided on 2026-05-26 that `envelope-fernet` is transitional
compatibility only. It must not be represented as production domain-bound
authenticated field encryption, and existing production ciphertext migration is
not best-in-class complete until production AEAD writes are enabled through an
approved rollout and existing ciphertext has migration evidence.

## Recommendation

Keep legacy Fernet as the default encrypted database-field write format until
maintainers approve an AES-GCM rollout for a deployment.

AES-GCM is the implemented AEAD candidate because it is already available
through the existing `cryptography` dependency, has broad deployment and
compliance support, and fits Hush Line's domain and AAD envelope design.
ChaCha20-Poly1305 is a reasonable non-FIPS alternative, but it does not offer
enough Hush Line-specific benefit to replace AES-GCM as the first production
AEAD target.

Do not add a new crypto dependency for this work. Revisit the decision only
after the following are complete:

- dual-read compatibility has been proven in production-like environments
- the migration runbook has completed staging rehearsal
- operator key backup and restore procedures are documented for the target
  format
- maintainers have explicitly approved changing the write algorithm for the
  target deployment

## Options Compared

| Option              | Fit for encrypted fields                                             | Primary benefit                                                                    | Primary risk                                                                                                  | Recommendation                    |
| ------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| Fernet continuation | Strong compatibility fit for current text columns and rollback needs | Existing deployed format; timestamp is already pinned to zero by Hush Line writes  | No AAD or field/domain binding without an outer envelope; larger ciphertext than AEAD for many values         | Keep for now                      |
| ChaCha20-Poly1305   | Good AEAD fit when deployments do not require FIPS-oriented choices  | Fast software AEAD with simple 96-bit nonce interface                              | Catastrophic nonce-reuse failure; weaker FIPS fit; no decisive advantage for current server-side field writes | Defer                             |
| AES-GCM             | Best AEAD fit for Hush Line's envelope and deployment constraints    | Existing dependency, common operational support, efficient ciphertext, AAD support | Catastrophic nonce-reuse failure; requires careful nonce generation and test vectors                          | Implemented explicit write option |

## Evaluation Criteria

### Compatibility And Migration Safety

Fernet continuation has the lowest immediate risk because all existing
encrypted-field values are Fernet tokens and the deployed model properties
already expect text ciphertext. The versioned Fernet envelope also preserves
dual-read behavior without changing schemas or default writes.

ChaCha20-Poly1305 and AES-GCM both require a versioned envelope for algorithm
identification, nonce storage, AAD schema identification, and rollback. AES-GCM
new writes require the widened envelope-ready schema and canonical AAD; existing
ciphertext must not be rewritten until legacy Fernet reads are proven and
migration tooling can verify every rewritten row.

### Nonce Generation And Misuse Resistance

AES-GCM and ChaCha20-Poly1305 both require a unique nonce for every encryption
under the same key. Reusing a nonce with the same key is a severe failure mode
for both candidates and can compromise confidentiality and integrity.

For Hush Line encrypted fields, the AEAD writer must:

- use a 96-bit random nonce from the operating system CSPRNG for every write
- store the nonce in the authenticated versioned envelope
- include algorithm, envelope version, AAD schema, domain, table, column, and
  immutable row identifiers in AAD
- fail closed on wrong domain, wrong row AAD, wrong key, malformed nonce, or
  malformed ciphertext
- never derive nonces from mutable user data, timestamps, row counts, primary
  keys alone, or retry counters

Random 96-bit nonces are acceptable for Hush Line's expected encrypted-field
write volume, but the migration helper should still count writes and surface
unexpected retry loops. If future write volume becomes high enough that random
nonce collision probability is no longer negligible, maintainers should
evaluate a deterministic nonce allocation scheme or a misuse-resistant AEAD in a
separate design.

Fernet hides nonce management from Hush Line but also prevents native AAD. The
outer envelope can provide algorithm agility, but it cannot make Fernet
ciphertext fail closed for wrong field context unless the envelope format itself
is authenticated by a separate AEAD.

### Dependency Surface And Maintenance Status

Fernet, AES-GCM, and ChaCha20-Poly1305 are all available from the existing
`cryptography` package. Choosing AES-GCM or ChaCha20-Poly1305 through that
package does not require a new runtime dependency.

Adding another crypto library would increase review and maintenance burden and
should require separate maintainer approval. Any production AEAD change should
stay on `cryptography` unless maintainers approve a specific, documented reason
to expand the dependency surface.

Fernet continuation, AES-GCM, and ChaCha20-Poly1305 therefore have the same
repository-level maintenance dependency today: keeping `cryptography` current
and passing dependency-audit checks. A future AEAD rollout should still review
the then-current `cryptography` release notes, security advisories, and
supported OpenSSL backend behavior before maintainers enable production writes.

### Ciphertext Size And Text Envelope Cost

Current Fernet storage is text-friendly but includes version, timestamp, IV,
PKCS7 padding, and HMAC overhead before base64url encoding. Hush Line pins the
Fernet timestamp to zero, which avoids per-write timestamp leakage but does not
reduce token size.

AES-GCM and ChaCha20-Poly1305 produce ciphertext with a 16-byte authentication
tag and require a stored nonce, typically 12 bytes. The binary overhead is
therefore about 28 bytes before JSON and base64url envelope encoding. For small
database-field values, the text envelope's JSON keys and base64 expansion are a
meaningful part of the stored value. For larger field values, AEAD ciphertext is
usually smaller than Fernet because it does not add block padding or a separate
HMAC field.

Hush Line should keep ASCII text envelopes for the next production format even
if the underlying AEAD emits bytes. Avoiding a text-to-binary column migration
is more important than the storage savings from raw binary columns during the
first algorithm change.

### FIPS And Deployment Constraints

Some deployments may require FIPS-validated cryptographic modules or FIPS-mode
OpenSSL behavior. In those environments, AES-GCM is the most plausible AEAD
candidate among the options, but operators still need to verify their exact
Python, `cryptography`, and OpenSSL build.

ChaCha20-Poly1305 should be treated as a non-FIPS-oriented option unless a
specific deployment has validated support. Fernet should not be assumed to
satisfy FIPS requirements as a complete construction; it combines primitives and
encoding through a library recipe rather than exposing an AEAD mode selected for
FIPS alignment.

Hush Line should not enable an algorithm switch solely for compliance wording.
Compliance-sensitive deployments need environment-specific validation and a
maintainer-approved rollout note.

## Test-Vector Strategy

AES-GCM production-write tests must include:

- official AES-GCM known-answer vectors for encryption and authentication
- Hush Line envelope vectors with fixed key, nonce, plaintext, domain, and AAD
- vectors for empty plaintext and representative field sizes, including TOTP
  secrets, email addresses, SMTP passwords, PGP keys, and custom field values
- negative vectors for wrong AAD, wrong domain, wrong key, truncated
  ciphertext, malformed nonce, malformed JSON, unknown version, and unknown
  algorithm
- compatibility tests proving legacy Fernet values and versioned Fernet
  envelopes remain readable while AES-GCM writes are enabled
- migration verification tests proving source plaintext and replacement
  plaintext match before any source ciphertext is overwritten

If ChaCha20-Poly1305 is reconsidered, use the same Hush Line envelope and
negative-vector strategy with official ChaCha20-Poly1305 known-answer vectors.

Test vectors must not contain production secrets, private keys, real disclosure
content, real notification addresses, or real user data.

## Decision Record

Hush Line keeps Fernet as the default production encrypted-field write format
and supports AES-GCM as an explicit production write-format option for new
values. The next production security value comes from compatibility, domain
separation, AAD contracts, and migration safety rather than from rewriting
existing Fernet ciphertext immediately.

The AES-GCM writer uses the existing `cryptography` dependency, the existing
versioned envelope prefix, stable AAD from `ENCRYPTED_FIELD_CONTRACTS`, random
96-bit nonces, and a test-vector suite before production write-format rollout.

The implementation path before any best-in-class existing-ciphertext migration
is: keep legacy Fernet and `envelope-fernet` reads during rollout, rehearse the
runbook against staging or restored-backup data, and require maintainer approval
before enabling AEAD writes for a deployment or rewriting existing ciphertext.
