# PQXDH and SPQR Browser Prototype

This isolated, synthetic prototype exercises `@getmaapp/signal-wasm` without
changing Hush Line production routes, chat state, wire formats, or CSP. It uses
only fictional peers. Reports contain public protocol metadata, ciphertext
hashes and sizes, timings, and pass/fail outcomes; they must never contain
plaintext, private keys, ratchet state, credentials, or production data.

The candidate and browser runner are exact-pinned in `package.json` and
`package-lock.json`. The lock records the npm SHA-512 integrity; `npm ci`
verifies the fetched tarball. The provenance script then verifies the installed
file inventory and reviewed SHA-256 hash of every published file, and records
the npm-published source `gitHead`. The implementation environment could not
resolve the npm registry, so those checks remain unexecuted rather than recorded
as passing.

Record the installed artifact hashes with `npm run provenance`. Generate the
CycloneDX SBOM with
`npm sbom --sbom-format cyclonedx > artifacts/sbom.cdx.json` and run
`npm audit --package-lock-only --json > artifacts/npm-audit.json`. Review both
outputs before attaching them as evidence; an unreviewed generated file is not
a passing vulnerability or license disposition.

## Automated engine run

Using the committed lock with the configured trusted npm registry, run from
this directory:

```sh
mkdir -p artifacts
npm ci
npm run provenance > artifacts/provenance.json
npm test
```

The Playwright projects exercise its bundled Chromium, Firefox, and WebKit
engines in fresh ephemeral contexts. WebKit emulation is not actual Safari,
Firefox is not Tor Browser, and a fresh Playwright context is not evidence for
each browser's user-facing private mode. Do not relabel these results.

The harness proves PQXDH by requiring consumption of the Kyber prekey. It parses
SignalMessage protobuf field 5 and the upstream SPQR v1 serialized header to
record independently observed epoch numbers. It then checks bidirectional
traffic, exported/imported sessions, an actual page reload from session storage,
dropped and reordered messages, replay rejection, 30 warm measurements, bundle
transfer, available heap/long-task metrics, state size, and ciphertext
amplification. The wrapper does not expose its remote-identity trust map, so the
report distinguishes session continuation from complete trusted-identity state
persistence and marks the latter acceptance check failed.

## Real-browser matrix

Start `npm run serve`, then open `http://127.0.0.1:4179/` in the exact browser
under review and choose **Run synthetic scenario**. Repeat in normal and private
modes on physical macOS Safari, iOS Safari, Firefox, Tor Browser, and Chromium.
Record the full browser/OS/device version and hardware alongside the downloaded
or copied non-secret JSON. Repeat with storage disabled and with quota pressure;
after refresh, the prototype must report unavailable state rather than retrying
with a classical or plaintext path.

The route `/?csp=conversation` applies the current authenticated-conversation
`script-src 'self'` policy. The candidate is expected to be blocked there. The
default prototype route adds only `'wasm-unsafe-eval'` so feasibility tests can
run in isolation. That is not approval to change production CSP.

## Evidence limits and open gates

This harness does not implement the official native libsignal reference peer,
and reports `reference_peer.status` as `not_run`. A passing G2 decision still
requires that pinned peer, actual named browser/private-mode results, reviewed
provenance/SBOM/audit/license evidence, comparison against the approved G1
baseline and budgets, named maintenance/security owners, and explicit human CSP
disposition. Keep issue `scidsg/hushline#2397` open until those artifacts are
linked to the exact revision.
