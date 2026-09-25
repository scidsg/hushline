# ADR-0001: Browser Protocol Candidate Gate

Status: **No-go**  
Date: 2026-09-24  
Decision gate: G2 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2367`

## Context

Hush Line needs an existing, maintained browser implementation of asynchronous
PQXDH setup and continuous hybrid PQ ratcheting. The implementation must retain
normal-login history, complete-copy confidentiality, two-party offline
delivery, browser restrictions, performance budgets, and the current security
claim limits. A package claim or a PQ handshake followed only by classical
ratcheting is insufficient.

The [candidate evaluation](candidate-evaluation.md) found one plausible WASM
wrapper, one divergent pure-TypeScript profile, and official libsignal as a
native reference peer. None has a complete Hush Line evidence set. The G1
contract also remains pending human approval, so a successful G2 result could
not silently choose among unresolved product/security decisions.

## Decision

Do not select or integrate a PQ chat protocol dependency at the reviewed
revisions. Do not change the production chat wire format, storage model, CSP,
or browser support claim.

`@getmaapp/signal-wasm` 0.6.6 remains the first candidate to re-evaluate because
it wraps the official libsignal revision and exposes the necessary session
operations. It is not approved now because:

1. the npm artifact is not tied here to an exact wrapper source commit and
   reproducible build/SBOM;
2. it implements round-3 Kyber1024 (`0x08`), not FIPS 203 ML-KEM, and that
   algorithm choice has not received Hush Line approval;
3. Hush Line has not independently observed multiple SPQR epochs or a
   reference-peer exchange across save/reload and delivery faults;
4. the required real-browser, restricted-storage, and performance matrix has
   not run;
5. the authenticated conversation route has not demonstrated WASM execution
   under its current CSP; and
6. no primary Hush Line maintainer and security-review backup are named for the
   dependency and wire lifecycle.

The pure-TypeScript candidate is not the fallback. Its divergent wire profile,
private protocol test evidence, rapidly changing public version/provenance, and
absence of independent review make it unsuitable as the reference needed to
validate itself. Official libsignal is the reference peer, not a browser build.
OpenMLS is not advanced because its reviewed public suite/browser support does
not satisfy this gate.

## Consequences

- G2 is a failed browser gate, so dependent production cryptographic work must
  not start and classical-only substitution does not count as progress.
- Existing E2EE behavior and its CSP remain unchanged.
- The evidence manifest records all unexecuted cases explicitly. A repository
  test prevents those missing cases from coexisting with a `go` decision.
- Kyber and ML-KEM names remain distinct in design and product material.
- No product or release copy may claim PQ account chat, continuous PQ refresh,
  browser support, interoperability, or an audit from this review.

## Costed Reconsideration

Reconsideration is a separate, time-boxed engineering spike after G1 approval
and named ownership. Planning estimate, not a delivery commitment:

<!-- prettier-ignore -->
| Work | Estimate |
| --- | ---: |
| Immutable package/source pin, two clean rebuilds, SBOM, license and vulnerability review | 3–4 engineer-days |
| Instrumented synthetic client plus official-libsignal reference peer and non-secret epoch evidence | 5–7 engineer-days |
| Save/reload, offline, loss/reordering, prekey exhaustion/replay, and restricted-storage cases | 4–5 engineer-days |
| Named desktop/mobile Safari, Firefox, Tor Browser, and Chromium runs on recorded hardware | 4–6 engineer-days |
| Thirty-run cold/warm benchmark corpus, CSP trace, report, and security-review disposition | 4–6 engineer-days plus 3–5 security-review days |

Expected gate cost: **20–28 engineer-days plus 3–5 security-review days** and
access to physical iOS/Safari hardware. A passing gate would still precede a
separately estimated product integration, migration, operations, and independent
security assessment; this ADR does not authorize or estimate those as committed
delivery work.

## Reconsideration Gate

A replacement ADR may change this decision only when it links:

1. the exact approved G1 commit and reviewer dispositions;
2. the candidate package integrity, exact source and dependency revisions,
   deterministic build inputs, two matching clean build hashes, SBOM, license
   disposition, and current vulnerability results;
3. non-secret logs proving PQXDH and at least two independently detectable
   post-handshake PQ epochs with a pinned official-libsignal peer;
4. passing reload, offline, loss/reordering, replay, prekey, private-mode, and
   storage-denial cases;
5. exact browser/OS/device results and all G1 benchmark measurements;
6. a no-expansion CSP result or explicit minimal-scope maintainer approval with
   regression tests; and
7. the named primary maintainer and security reviewer for updates and incidents.

Human approval is required. A merge, green CI run, package README, or automated
review cannot supply any of these dispositions by itself.
