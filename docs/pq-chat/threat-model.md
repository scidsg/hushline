# PQ Chat Threat Model and Revocation Boundaries

Status: **Proposed for human approval**  
Scope: future hybrid-PQ account chat under the
[unchanged-UX contract](unchanged-ux-contract.md)

This document extends, but does not replace, the repository
[threat model](../THREAT-MODEL.md) and current
[two-way chat E2EE reference](../TWO-WAY-CHAT-E2EE.md). It defines security
boundaries before selecting protocol details. Component names such as “archive
key,” “prekey,” and “ratchet state” are roles, not selected constructions.

## Assets and Security Objectives

Highest-sensitivity assets are conversation plaintext, unlocked account roots,
archive/content keys, browser private keys, unused private prekeys, live ratchet
state, and recovery material. Public keys, consumed-prekey identifiers,
ciphertext, participant records, and protocol versions require integrity even
when they are not secret.

Objectives:

1. Every new content-bearing participant/archive copy receives complete-copy
   hybrid PQ confidentiality or the write fails.
2. Only authenticated conversation participants can retrieve ciphertext or
   append a valid message, subject to the explicit classical-authentication
   limitation.
3. A passive store-now/decrypt-later attacker cannot recover a new copy by
   breaking only its classical confidentiality component.
4. Compromise scope, recovery, and revocation limits are stated without
   implying guaranteed endpoint erasure.
5. Metadata exposure, anonymous-flow separation, and trustworthy-client-code
   assumptions remain visible.

## Adversaries in Scope

- A passive network or storage adversary who records encrypted content now and
  later obtains a cryptographically relevant quantum computer.
- A database/blob/backup reader or writer who can copy, delete, replay, reorder,
  or substitute server-held records but cannot initially execute code in a
  participant browser.
- A malicious conversation participant who controls their account, browser,
  keys, and plaintext copies.
- An account attacker who steals a password, authenticated session, unlocked
  browser state, or recovery capability.
- A browser-local attacker such as a malicious extension, injected script,
  device malware, or forensic operator.
- A compromised Hush Line server, administrator, build pipeline, dependency, or
  deployment that can alter responses or served JavaScript.
- An availability attacker who withholds prekeys/messages, exhausts prekeys,
  rolls back public state, or forces retries.

Quantum capability does not turn a passive recorder into a trusted endpoint.
It does, however, invalidate claims that rely only on classical public-key
confidentiality or signatures.

## Explicit Non-Goals and Claim Limits

- PQ confidentiality does not make account chat anonymous or metadata-private.
- This gate does not promise PQ account authentication, PQ server
  authentication, PQ key transparency, deniability, traffic-flow secrecy, or
  resistance to endpoint screenshots/copying.
- It does not protect plaintext or keys handled by malicious served JavaScript,
  a compromised browser/device, or a malicious participant.
- It does not retroactively protect pre-activation classical copies.
- It does not guarantee secure deletion from browser memory, swap, caches,
  backups, logs, extensions, or forensic images.
- It does not create server-side plaintext recovery after password reset.

## Trust and Compromise Boundaries

### Server and delivery path

The server authenticates accounts, authorizes participant routes, distributes
public key/prekey material, stores ciphertext and metadata, orders messages,
sends generic notifications, and serves the cryptographic client.

Trusted for: availability, correct participant metadata and ordering,
consistent public-state delivery, and serving reviewed client code.

Not trusted with: conversation plaintext, unwrapped account/archive secrets,
private prekeys, or live ratchet message keys.

Compromise consequences: the server can observe metadata, deny or fork service,
substitute public state, replay records, and—most critically—serve JavaScript
that steals plaintext and keys. Classical signatures/context binding can expose
some stored-record tampering but do not protect a browser executing malicious
served code. Database-only compromise must not be sufficient to decrypt new
hybrid copies.

### Account unlock root

This is the browser-held secret unlocked from the normal account-password flow
and used directly or indirectly to recover durable chat secrets/history.

Trusted for: granting a successfully authenticated browser access to retained
history without a second chat credential.

Compromise consequences: an attacker with the root plus available ciphertext
can access every key/copy in its derivation or wrapping scope. Password change
that merely rewraps the same root does not repair a copied root. Password reset
without the old root cannot recover old history and must create a new trust
epoch if chat continues.

### Archive keys and encrypted history

Archive keys protect durable participant copies that must survive tab closure,
fresh browsers, and discarded ratchet message keys. They may be hierarchical or
versioned; this gate does not choose the design.

Trusted for: retained-history availability and confidentiality against a
storage-only adversary.

Compromise consequences: every retained copy decryptable by the compromised
archive secret is exposed. Rotation protects only copies outside that secret's
scope. Re-encryption cannot make an already copied key or plaintext secret
again. Archive availability deliberately limits claims that ratchet deletion
alone provides forward secrecy for retained history.

### Browser device and page

The browser receives account credentials, client code, plaintext, unlocked
roots, private keys, and live protocol state. A tab may temporarily share an
unlocked bundle with another same-session tab.

Trusted for: correct cryptographic execution, randomness, origin isolation,
storage isolation, UI integrity, and best-effort cleanup.

Compromise consequences: malicious code or a device attacker can read plaintext
at entry/display, steal secrets, forge user actions, and preserve copies outside
Hush Line. Logout, account deletion, or remote session revocation cannot erase
material already exfiltrated. Browser APIs do not provide a verifiable secure
erase primitive.

### Prekeys

Prekeys are server-distributed public material that lets a sender establish new
hybrid state while a recipient is offline. Their exact type and count are not
selected here.

Trusted properties required of a design: public/prekey identity binding,
one-time or otherwise explicitly bounded use, atomic server consumption where
promised, exhaustion handling, versioning, and downgrade/replay detection.

Compromise consequences: stolen unused private prekeys can expose sessions
created from them according to the selected protocol. A malicious server can
withhold, replay, exhaust, or substitute public prekeys; classical identity
authentication cannot support a PQ-authentication claim. Revoking an unused
prekey can prevent future accepted use after clients learn the revocation, but
cannot invalidate an encapsulation or session already created with it.

### Ratchet state

Ratchet state includes current chain/root keys, message keys, counters, skipped
key cache, and any state needed for out-of-order delivery. The selected design
must distinguish ratchet transport/state from durable archive access.

Trusted for: only the precise forward-secrecy and post-compromise-recovery
properties demonstrated by the selected protocol.

Compromise consequences: the attacker reads the currently derivable window and
may send forged messages where authentication keys permit. Deleting old message
keys can reduce past exposure only if no archive/root copy can decrypt the same
content and if deletion was effective. Post-compromise recovery begins only
after the required uncompromised contribution/exchange; server withholding or
continued endpoint compromise can prevent healing.

## Revocation and Repair Matrix

<!-- prettier-ignore -->
| Revocation / response | Can repair | Cannot repair |
| --- | --- | --- |
| Revoke authenticated web sessions / change server chat-session identifier | Blocks later API use by those sessions; prevents stale tab-storage restoration when identifiers differ | Erase captured ciphertext, plaintext, roots, archive keys, prekeys, or ratchet state; stop offline decryption of stolen material |
| Change password with old password and rewrap | Protects the still-secret root from later guesses of the old password; revokes sibling sessions under current behavior | Repair an already stolen root/archive key; add PQ protection to old copies |
| Reset password without old secret | Restores account access in a new epoch and can protect future chat after new keys are established | Recover old locked history; prove old browser secrets were erased; revoke plaintext already read |
| Rotate account unlock root / archive key | Limits future/newly re-encrypted copies to the new scope after authenticated distribution | Protect copies or keys captured before rotation; silently preserve history if the old root is unavailable |
| Revoke/rotate a participant identity or signing key | Rejects future writes under the revoked key once all verifiers have current state; makes change visible where continuity checks exist | Make prior classical authentication PQ-secure; undo accepted messages; defeat a server that presents a fork without an independent transparency mechanism |
| Remove or consume a prekey | Prevents later legitimate selection if server/client state is current and consumption is atomic | Undo a session already established from it; protect against a copied private prekey; force a malicious server to disclose replay/fork without additional mechanisms |
| Advance/reset ratchet state | Can limit future derivation and, after an uncompromised exchange, may heal the selected ratchet | Protect durable archive copies; guarantee deletion of browser state; heal while the endpoint remains compromised |
| Delete one participant's conversation | Removes current server access/copies according to participant-local semantics | Delete the other participant's copy, backups, captured ciphertext, browser plaintext, or attacker-held keys |
| Delete account | Removes server-held account data through current relationships and blocks future normal access | Retract another participant's plaintext/copy or prove deletion from backups/endpoints |
| Deploy fixed server/client code after compromise | Stops the fixed version from repeating the flaw once users receive it and rotate affected state | Restore confidentiality for plaintext/secrets captured by the malicious version or prove which users were unaffected |

Revocation is accepted only after the client has authenticated current state.
Server acknowledgement alone is not proof that a malicious or forked server
stopped serving compromised material.

## Required Abuse and Failure Cases

A future design and test plan must cover:

- omission of the sender, recipient, or archive copy;
- one classical-only copy mixed into an otherwise hybrid write;
- PQ component stripping, algorithm/version confusion, malformed keys, and
  unsupported capabilities;
- public key/prekey substitution, reuse, replay, exhaustion, rollback, and
  concurrent consumption;
- message/copy replay across conversation, sender, recipient, purpose, or key
  epoch;
- partial persistence, timeout, browser retry, duplicate submission, and
  notification failure;
- fresh-browser history, same-tab refresh, multiple tabs, offline recipient,
  password change, password reset, participant deletion, account deletion, and
  legacy-history coexistence;
- storage denial, private browsing, missing cross-tab APIs, missing Web Crypto,
  and disabled JavaScript;
- compromised current ratchet state, compromised archive root, and rotation
  before/after compromise; and
- CSP/supply-chain regressions and plaintext/key leakage through requests,
  responses, logs, exceptions, analytics, email, or exported artifacts.

## Security Messaging Rules

Product, documentation, release, and support copy must say “hybrid
post-quantum confidentiality for new account-chat copies” only after the
complete-copy gate passes. It must pair that claim with the classical
authentication and trustworthy-served-JavaScript limits. It must not describe
the feature as anonymous, quantum-safe without qualification, securely
erasable, retroactive, independently audited, or validated by user research.
