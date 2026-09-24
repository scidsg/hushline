# Post-quantum OpenPGP compatibility verification

Verified locally on 2026-09-23, starting from commit
`d889937bfc926692238e31ddd901b9e197e39937`, with the fix isolated on current main
(`0f5d171a`). These changes are not a production
deployment or evidence of the hosted service's current capabilities.

## Findings and fix

Browser submissions use `assets/js/client-side-encryption.js` and OpenPGP.js.
Manual key registration, Proton import validation, server fallback, notifications,
and export encryption use the helpers in `hushline/crypto.py`, backed by pysequoia.
Both paths must support the recipient's certificate.

The original lockfiles selected `openpgp` 6.3.0 and pysequoia 0.1.25.
OpenPGP.js 6.3.0 and the current upstream npm release, 6.3.1, failed to encrypt
to each of the three RFC test profiles below. The first two parsed but had no
usable encryption key; the ML-DSA primary key failed to parse. The original
backend rejected both v6 certificates and parsed the v4 certificate but could
not encrypt to its PQC subkey.

Upstream [PQC implementation PR 2022](https://github.com/openpgpjs/openpgpjs/pull/2022)
was merged on 2026-07-10 for v7. A merge into development does not make PQC
available in the [6.3.1 release](https://github.com/openpgpjs/openpgpjs/releases/tag/v6.3.1).
The published [Proton fork](https://github.com/ProtonMail/openpgpjs),
`@protontech/openpgp` 6.3.1, implements the tested algorithms.

The fix pins `openpgp` to the npm alias `npm:@protontech/openpgp@6.3.1` and pins
[pysequoia 0.1.35](https://pypi.org/project/pysequoia/0.1.35/). Three encryption
calls now use the updated Sequoia API: `encrypt(data, recipients=certificates)`.
This is a change of JavaScript package publisher, not an ordinary upstream
patch upgrade. Track both projects' security advisories and revisit the alias
when upstream publishes a PQC-capable release. No crypto validation or CSP
restrictions were disabled.

## Exact tested profiles

The public test fixtures come from [RFC 9980 Appendix A](https://www.rfc-editor.org/rfc/rfc9980.html#appendix-A).
All imported public keys were ASCII-armored `PGP PUBLIC KEY BLOCK` certificates.
Decryption used the corresponding unprotected ASCII-armored `PGP PRIVATE KEY
BLOCK` test keys, held only by the test harness.

| RFC fixture | Key packet version | Primary key / certificate signatures | Encryption subkey               |
| ----------- | ------------------ | ------------------------------------ | ------------------------------- |
| A.1         | v6                 | Ed25519, algorithm 27                | ML-KEM-768+X25519, algorithm 35 |
| A.2         | v4                 | Ed25519, algorithm 27                | ML-KEM-768+X25519, algorithm 35 |
| A.3         | v6                 | ML-DSA-65+Ed25519, algorithm 30      | ML-KEM-768+X25519, algorithm 35 |

All three pass key validation, server text and binary-payload round trips,
JavaScript-to-Sequoia decryption, Sequoia-to-JavaScript decryption, and browser
submission encryption followed by JavaScript decryption. Ciphertext packet
assertions require algorithm 35, preventing an accidental classical fallback
from being counted as a PQC success. Browser coverage includes padded message
fields, whole email bodies, and per-recipient email fields. The compiled
submission handler runs in Chromium under a synthetic HTTPS origin with
`script-src 'self'` and no external network service. The harness intercepts
submission; it does not test a live hosted inbox or external mail delivery.

The JavaScript output examined for these profiles uses v6 PKESK and v2 SEIPD,
AES-256 (algorithm 9), and OCB (AEAD algorithm 2). The v4 certificate therefore
does not imply a legacy v3 PKESK/v1 SEIPD output format.

Hush Line encrypts unsigned messages. Accepting the ML-DSA primary key tests
certificate validation; it does not establish a Hush Line message-signing
feature. Binary message payloads were tested, but binary key-file import was
not. PEM/DER keys, raw ML-KEM keys, legacy Kyber formats, ML-KEM-1024+X448,
ML-DSA-87+Ed448, SLH-DSA, passphrase-protected private keys, customer-generated
keys, GnuPG, and external mail clients are outside this verification.

PQC compatibility here applies to the tested OpenPGP recipient profiles.
In-app chat still uses ECDH P-256/AES-GCM and ECDSA P-256. Adding a PQC recipient
does not make another classical recipient's copy quantum-resistant.

## Validation and remaining release gate

- Focused Python suite: 287 passed, covering crypto, native dependencies,
  settings, notifications, resend, security headers, and the initial three PQC tests.
- Expanded focused suite on the PR branch: 293 passed, including nine PQC tests.
  These cover cross-library decryption, Settings key import, and stored submissions
  with no JavaScript encryption payload.
- Compiled browser PQC suite: 3 passed in Chromium build 1243. An existing local
  browser was selected through a temporary Playwright config because the matching
  browser download stalled. The committed test uses the normal project config.
- `make lint CMD='docker compose -p hushline run --rm --no-deps app'`: passed.
- `npm run build:prod`: passed; existing Sass deprecation warnings remain.
- Full and runtime-only npm audits: zero known vulnerabilities.
- `make audit-python`: no known vulnerabilities.
- Full `make test` with coverage and `--skip-local-only`: 2,340 passed, four
  skipped, one deselected, one expected failure; 99% aggregate coverage. Test
  database teardown now drops each generated database; previously the fixture
  retained one database per test, eventually filling Docker's disk.
- GitHub's compiled PQC browser tests also passed with the normal pinned browser.
  Full required CI and review remain release gates. The RFC private test keys
  are publicly specified test credentials; no scanner exemptions were added.
- CI now installs the JavaScript lockfile for cross-library tests and runs the
  compiled PQC browser suite as a separate job.

Reproduce after installing both lockfiles and building browser assets:

```sh
docker compose exec -T app poetry run pytest tests/test_pqc.py -q
npm run playwright:e2ee -- pqc.spec.js
```

`tests/testdata/openpgp-pqc.json` contains public RFC test secrets, never real
account keys. Never use them to receive actual messages. No customer messages
or private keys were used, and no customer response was sent.

## Customer response draft

Yes—we have verified Hush Line's updated OpenPGP encryption with ASCII-armored
v4 and v6 keys using ML-KEM-768+X25519 encryption subkeys, including a v6 key
with an ML-DSA-65+Ed25519 primary key. We tested browser encryption, server-side
encryption, and successful decryption across two independent implementations.

This compatibility required dependency updates and applies to the tested key
profiles. The update is verified locally and still needs full release validation
and deployment before we can confirm availability on the hosted service.
