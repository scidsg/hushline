# PQ Chat Browser Protocol Candidate Evaluation

Status: **No-go at reviewed revisions; G2 is not closed as a successful gate**  
Issue: `scidsg/hushline#2367`  
Parent epic: `scidsg/hushline#2365`  
Recorded: 2026-09-24  
Repository baseline: `37abae6e11dd9c0e8306f5e962ae97504f5c0888`

## Scope and Evidence Standard

This review asks whether a maintained, existing implementation can provide a
browser PQXDH handshake and continuous hybrid post-quantum ratcheting under the
[G1 product and security contract](unchanged-ux-contract.md). It does not design
a ratchet, change Hush Line production code, or treat a README, a successful
handshake, or ordinary Double Ratchet traffic as proof that SPQR epochs ran.

The result is deliberately a no-go. No reviewed candidate has committed Hush
Line evidence for all of these gates:

- an exact, reproducible source-to-package pin and complete SBOM/audit result;
- offline setup and bidirectional traffic through independently observed PQ
  refresh epochs, including reload and dropped/reordered delivery;
- a reference-peer or cross-implementation conformance run;
- the required named browser/version, private-mode, and restricted-storage
  matrix;
- the G1 latency, transfer, memory, blocking, storage, and amplification
  measurements; and
- route-specific CSP execution without an unapproved expansion.

The detailed status is data, not prose, in
[`g2-evidence.json`](g2-evidence.json). A repository test rejects a `go`
decision while any required result is missing.

## Candidate Inventory

### `@getmaapp/signal-wasm` 0.6.6 — primary candidate

This is the closest fit. The published package and source describe a
browser-first WASM wrapper over libsignal, PQXDH setup, serializable session and
prekey stores, and Triple Ratchet traffic. The reviewed source manifest pins
libsignal `v0.101.0` at
`b056faa6dd02961cff24064c54c089c52e1a0753`, `spqr` 1.5.3 through that
lock graph, `wasm-bindgen` 0.2.126, and both browser `getrandom` lines. The
wrapper and libsignal are AGPL-3.0-only, which is compatible in principle with
Hush Line's AGPL-3.0 codebase but still requires a distribution-notice review.

The KEM is **round-3 Kyber1024**, serialized with libsignal key type `0x08`.
It is not FIPS 203 ML-KEM. The wrapper's 0.6.6 changelog states that libsignal's
`mlkem1024` module is behind an off-by-default feature, with key type `0x0A`,
and that the wrapper does not enable it. The required Kyber prekey argument to
`processPreKeyBundle` makes PQXDH mandatory in the wrapper's exposed setup path;
there is no reviewed wrapper flag for a classical-only session. One-time
classical and Kyber prekey tombstoning remains an application responsibility.

Sources reviewed:

- [package listing and API](https://www.npmjs.com/package/@getmaapp/signal-wasm)
- [source manifest](https://github.com/getmaapp/signal-wasm/blob/main/Cargo.toml)
- [0.6.6 changelog](https://github.com/getmaapp/signal-wasm/blob/main/CHANGELOG.md#066---2026-08-19)
- [pinned libsignal revision](https://github.com/signalapp/libsignal/tree/b056faa6dd02961cff24064c54c089c52e1a0753)
- [Signal PQXDH revision 3](https://signal.org/docs/specifications/pqxdh/)
- [Signal Double/Triple Ratchet specification](https://signal.org/docs/specifications/doubleratchet/)

The pin is not sufficient for a go decision. The reviewed public material does
not bind the npm tarball to an exact wrapper commit in this repository, provide
a reproducible-build attestation, or provide a Hush Line-generated SBOM and
vulnerability result. GitHub reports no published libsignal security advisory,
but absence from that single channel is not a dependency vulnerability audit.
The wrapper's dated security report covers an older release and is not an
independent audit of 0.6.6.

Most importantly, no committed result exposes or independently verifies two or
more completed SPQR epochs. Ciphertext round trips alone cannot distinguish
continuous PQ contribution from PQXDH followed by only classical ratcheting.
The upstream instructions mention headless Chrome and Firefox, but publish no
exact successful browser matrix for Safari/iOS, Tor Browser, private mode, or
quota-denied storage. They also do not measure Hush Line's budgets.

### Official `signalapp/libsignal` v0.101.0 — reference peer only

Official libsignal is actively maintained and contains the protocol
implementation wrapped above, but Signal's published Node package carries
native libraries for desktop operating systems. It is not a supported browser
or WASM distribution. Signal also states that use outside Signal is unsupported
and its APIs may change without notice. It is therefore suitable as the
independent reference peer for a future harness, not as Hush Line's browser
dependency.

Revision: `b056faa6dd02961cff24064c54c089c52e1a0753` (`v0.101.0`)  
License: AGPL-3.0-only  
Source: [signalapp/libsignal](https://github.com/signalapp/libsignal/tree/b056faa6dd02961cff24064c54c089c52e1a0753)

### `@open-e2ee/signal-protocol-sdk` 5.0.0 — screened out

The package describes a pure-TypeScript browser profile with FIPS 203
ML-KEM-1024 PQXDH (`0x0A`) and an ML-KEM-768 Braid/SPQR path. It explicitly is
not wire-compatible with Signal Messenger or libsignal and has no independent
firm audit. Its assurance document says the protocol and conformance tests are
private rather than independently reproducible from the public export.

The public provenance was also changing during review: the npm listing reported
5.0.0 while indexed documentation and the repository source manifest described
different major versions and license metadata. Without an immutable source
revision matching the package, public vectors, and a separately maintained
reference implementation for its divergent wire profile, it cannot satisfy the
reference-peer or reproducibility gate.

Sources reviewed:

- [npm package](https://www.npmjs.com/package/@open-e2ee/signal-protocol-sdk)
- [security model](https://github.com/open-e2ee/signal-protocol-js/blob/main/docs/SECURITY.md)
- [assurance limits](https://github.com/open-e2ee/signal-protocol-js/blob/main/docs/ASSURANCE.md)

### Classical browser ports — screened out

`@privacyresearch/libsignal-protocol-typescript` 0.0.16 (GPL-3.0-only,
published in 2023) and the reviewed `main` branch of
`positive-intentions/signal-protocol` document X3DH and Double Ratchet browser
implementations, not the required PQXDH plus SPQR/Triple Ratchet profile. The
latter also labels itself unaudited. They cannot pass the gate through a
classical-only substitution.

Sources reviewed:

- [Privacy Research package](https://www.npmjs.com/package/@privacyresearch/libsignal-protocol-typescript)
- [Positive Intentions source](https://github.com/positive-intentions/signal-protocol)

### OpenMLS — not advanced

OpenMLS was not necessary to advance because multiple browser-oriented Signal
profiles existed for screening. Its published supported ciphersuites are
classical X25519/P-256 suites; `wasm32-unknown-unknown` is built but listed as
unsupported and not tested. Adopting MLS for a two-party account-chat spike
would also change the protocol family without satisfying this ticket's
continuous-PQ evidence requirement.

Source: [OpenMLS support matrix](https://github.com/openmls/openmls#supported-platforms)

## Browser, Storage, and CSP Result

No Hush Line browser execution result was produced, so browser versions,
hardware, operating systems, private-mode behavior, and quota behavior are
intentionally `null` or `not_run` in the evidence manifest. Upstream claims are
not copied into the result column.

Hush Line currently grants `'wasm-unsafe-eval'` to the profile intake routes
because of the existing OpenPGP client, but the authenticated conversation
route has `script-src 'self'` and does not grant it. The global policy already
has `worker-src 'self' blob:`. A WASM candidate must therefore prove whether its
production build executes on the conversation route under the current policy.
Adding `'wasm-unsafe-eval'` to that route would be a CSP expansion requiring
explicit maintainer approval and a narrowly scoped regression test. No CDN is
acceptable, and none was added by this review.

## Performance and Interoperability Result

Cold/warm latency, transfer size, memory, main-thread blocking, persisted state,
and ciphertext amplification were not measured. No synthetic fixture can
legitimately contain numbers until it records the exact package integrity,
production bundle, browser build, hardware, network profile, corpus, and at
least 30 timing runs required by G1.

No reference-peer transcript was produced. A future test must use official
libsignal at the same pinned revision as one endpoint and must record only
public keys, protocol metadata, ciphertext hashes/sizes, state-transition
counters, and pass/fail assertions. Plaintext, private keys, shared secrets,
message keys, and serialized private state must never enter the evidence log.

## Maintenance and Update Responsibility

No individual Hush Line maintainer is named for this new cryptographic supply
chain. That is a blocking result, not an assignment for an agent to invent.
Before reconsideration, maintainers must record one primary owner and one
security reviewer responsible for upstream release monitoring, source-pin and
SBOM refreshes, advisories, browser regressions, wire migrations, prekey
operations, emergency rollback, and removal. A generic team name or Dependabot
configuration is not sufficient.

## Acceptance Traceability

<!-- prettier-ignore -->
| Issue criterion | Evidence and disposition |
| --- | --- |
| Revisions, algorithms, wire, PQ flags, license, reproducibility, vulnerabilities, ownership | Candidate inventory and manifest `provenance`; partial facts recorded, remaining gates block |
| Offline setup, bidirectional PQ epochs, reload, loss/reordering, reference peer | Manifest `protocol_scenarios`; all `not_run`, so README/handshake claims cannot pass |
| Safari/iOS, Firefox, Tor Browser, Chromium, private/restricted storage | Manifest `browser_matrix`; all `not_run` with exact versions intentionally absent |
| Latency, transfer, memory, blocking, storage, amplification | Manifest `benchmarks`; all `not_run` and no fabricated values |
| Existing route-specific CSP | CSP review above and manifest `csp`; conversation-route execution remains unverified and no policy changed |
| Go/no-go ADR and costed recommendation | [ADR-0001](adr-0001-browser-protocol-candidate.md); no-go with explicit reconsideration cost |

This is engineering discovery, not production code, user research, or an
independent security audit. It closes no release gate and makes no PQ product
claim.
