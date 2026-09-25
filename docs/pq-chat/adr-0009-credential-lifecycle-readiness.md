# ADR-0009: PQ Chat Credential-Lifecycle Readiness

Status: **Blocked before implementation**

Date: 2026-09-25

Decision gate: G10 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2375`

## Context

G10 must preserve the existing password, unlock, and session experience while
adding honest lifecycle behavior for PQ chat devices, transport sessions, and
archive epochs. A password change made with the current unlock secret must
rewrap the complete approved hierarchy without losing retained history. A
password reset without that secret must keep old history locked and explain
that the server cannot recover it. Routine fresh-browser login must recover
authorized history without an existing device or pairing ceremony.

Compromise recovery is a separate operation from password rewrapping. Device
revocation must stop the revoked device from publishing or claiming prekeys and
from receiving new transport or archive access. It must replace affected
sessions and rotate future archive access under a defined atomic ordering for
stale offline devices and concurrent sends. Rotation cannot retract plaintext,
ciphertext, or keys already copied by an attacker, and a stolen archive key
continues to decrypt every retained copy within its old scope.

These behaviors require G5's authenticated device/prekey lifecycle, G8's
archive hierarchy and epoch lifecycle, and G9's atomic complete-copy delivery.
All three artifacts are present on this branch, but all three record blocked
decisions and no production implementation. The machine-readable
[G10 readiness record](g10-readiness.json) pins those findings, the required
credential changes, and the lifecycle evidence that cannot safely be produced
yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G5 / `scidsg/hushline#2370` | Accepted authenticated device membership, capability binding, bounded prekeys, atomic claim, revocation, and cleanup | Commit `f9ba0777a5a4029a1c95bac3e5fed6c7199b9229`; [ADR-0004](adr-0004-device-prekey-readiness.md) and [readiness record](g5-readiness.json) | **Unsatisfied:** G5 is blocked before implementation and supplies no device, membership, prekey, revocation, or cleanup implementation |
| G8 / `scidsg/hushline#2373` | Accepted account-root/archive hierarchy with wrapping, epochs, fresh-browser recovery, rotation, retention, deletion, and compromise limits | Commit `b7fd9a2292dd7c2f0311380a2180b2f62822e553`; [ADR-0007](adr-0007-pq-archive-readiness.md) and [readiness record](g8-readiness.json) | **Unsatisfied:** G8 is blocked before implementation and supplies no archive keys, wrapping context, epoch transition, recovery, or deletion implementation |
| G9 / `scidsg/hushline#2374` | Accepted atomic complete-copy delivery with current device/archive authorization, stable retry, and commit-coupled acknowledgement | Commit `4df7845b5d5a494f3314e24e3d8b551d99458878`; [ADR-0008](adr-0008-protected-delivery-readiness.md) and [readiness record](g9-readiness.json) | **Unsatisfied:** G9 is blocked before implementation and supplies no protected send, current-membership copy inventory, atomic commit, idempotency, or acknowledgement implementation |

A merged readiness artifact, issue order, or the existing classical chat-key
lifecycle is not proof that a gate passed. G10 cannot infer which secrets are
wrapped by the password-derived key, which device or archive records authorize
new copies, or where revocation and a concurrent send linearize.

## Decision

G10 is blocked before implementation. Do not change production password,
session, device, archive, or deletion paths until G5, G8, and G9 are accepted
and available on `codex/epic-2365` as production implementations with exact
reviewed contracts. In particular, do not:

- treat rewrapping an unchanged root as revocation of a copied root, device
  secret, archive key, prekey, ratchet state, or plaintext;
- make password reset recover an old unlock root at the server, silently erase
  old ciphertext, or describe unavailable old history as recoverable;
- let a revoked or stale device publish or claim new prekeys, receive new
  archive wrappers or required delivery copies, or restore state under an old
  membership, session, or epoch identifier;
- rotate only the password wrapper after device, unlock-root, or archive-key
  compromise and claim that future content is protected;
- accept a concurrent send against a stale device inventory or archive epoch,
  partially commit old/new-epoch copies, or regenerate ciphertext after an
  ambiguous result; or
- claim secure browser erasure, retroactive repair, real-browser evidence, or
  independent review that has not been supplied.

No production route, model, migration, browser asset, template, session,
account-deletion path, CSP, dependency, or security claim is changed by this
decision. Existing password-change rewrapping, password-reset locking, logout,
session invalidation, and conversation behavior remain unchanged.

## Deferred Lifecycle Contract

<!-- prettier-ignore -->
| Area | Evidence required after the prerequisites pass | Current disposition |
| --- | --- | --- |
| Password change with current secret | Browser unwraps the accepted account hierarchy, rewraps every required unchanged secret under the new password-derived wrapping key, and commits the new wrappers and password atomically before preserving history; failures preserve the old password and hierarchy; existing prompt and sibling-session revocation behavior remains | Blocked; G8 defines no accepted hierarchy, wrapping context, or transaction |
| Password reset without old secret | Old archive/history scope remains locked; reset creates a separately identified future trust epoch without server recovery of old secrets; accessible copy states the limitation; other participants' authorized copies are not corrupted | Blocked; G8 defines no reset/new-epoch or retained-copy contract |
| Routine fresh browser | Normal account login and existing 2FA unlock all authorized retained history without an existing device, recovery phrase, chat password, QR code, or pairing step | Blocked; G5/G8 supply no enrollment or archive recovery implementation |
| Device revocation | One authenticated transition tombstones the device and its unused prekeys, rejects later publication/claim and new device/archive grants, replaces affected transport sessions, and rotates future archive access | Blocked; G5 and G8 supply no revocation or epoch-transition boundary |
| Stale/offline device | A stale device cannot restore or send using superseded membership, transport, chat-session, or archive epochs; reconnection authenticates current state and uses existing account UX to recover or explains the security exception accessibly | Blocked; membership freshness and recovery states are unspecified |
| Concurrent sends and revocation | A reviewed linearization point makes a complete send commit wholly before revocation or reject/retry wholly against the new membership and archive epoch; no partial old/new inventory or duplicate side effect is accepted | Blocked; G9 supplies no complete-copy transaction or stable retry result |
| Logout, expiry, and browser clearing | In-memory and session-scoped secrets are best-effort cleared or locked; old chat-session identifiers cannot restore them; pending operations stop safely; normal login in a fresh browser recovers retained authorized history | Blocked; the new device/archive state and cleanup inventory do not exist |
| Emergency exit | When available from an authenticated unlocked context, activation immediately locks and best-effort clears local chat secrets before navigation; any server invalidation must not delay the safety exit; keyboard and assistive-technology behavior remains usable | Blocked; the new local state inventory and server-session contract do not exist |
| Account deletion | Server-held account device, prekey, wrapper, archive-copy, retry, and authorization state is removed under the accepted deletion/backup contract without corrupting remaining participants' history or resurrecting deleted state | Blocked; G5/G8/G9 supply no production records or deletion contract |

## Compromise-Response Boundaries

The future implementation and user guidance must distinguish these responses:

<!-- prettier-ignore -->
| Compromised material | Required change to protect eligible future content | What remains exposed or unchanged |
| --- | --- | --- |
| Password only, while the unlock root stayed secret | Change the account password and rewrap the unchanged hierarchy; revoke sibling authenticated sessions under existing behavior | Captured old password verifiers/wrappers remain attack evidence; rewrapping does not repair any root or key that was also copied |
| Authenticated web session only | Revoke server and chat-session identifiers; reject pending work authorized only by the stale session; revoke any attacker-enrolled device separately | Already read plaintext and exported state cannot be recalled; cryptographic keys do not rotate unless their exposure scope requires it |
| Device private state or unused private prekeys | Revoke device membership and prekeys; replace affected transport sessions after an uncompromised contribution; rotate future archive epoch/access grants; reject the stale device from new copies | Prior accepted sessions, copied plaintext, and archive copies remain exposed according to the compromised keys' exact scope |
| Archive epoch key | Create a new archive epoch and wrappers, authorize only current devices, and place every eligible future archive copy exclusively under the new scope | The stolen key still decrypts applicable old/retained copies and captured ciphertext; password change or rewrapping alone does not revoke it |
| Account unlock root | Rotate the root and every device, identity, prekey, archive, or wrapper secret in its derivation or wrapping scope; revoke sessions; change the password too if it was exposed | Old ciphertext and keys already captured under the compromised root remain exposed; history cannot be silently preserved when the old root is unavailable |
| Identity/signing key or live ratchet state | Rotate the compromised identity and authenticated membership as applicable; replace affected sessions with an uncompromised contribution; rotate archive access if that state was exposed | Previously accepted messages are not undone; classical authentication is not made PQ-secure; healing is not claimed while the endpoint remains compromised |

Password rewrapping is therefore an availability-preserving password operation,
not a general compromise-recovery operation. The exact rotation set must be
derived from the accepted key hierarchy and demonstrated at the implementation
commit; it cannot be guessed from the current single chat-key model.

## Required Validation After Unblocking

The implementation must provide linked, non-secret evidence for:

1. password change with current-secret success and injected failure at every
   unwrap, rewrap, persistence, password, and session-rotation boundary,
   proving atomic rollback, preserved history, and unchanged prompts;
2. password reset without the old secret in Chromium, Firefox, and WebKit,
   proving clear locked-history messaging, a separate future epoch, no server
   recovery, and no corruption of another participant's retained history;
3. routine fresh-browser login with existing 2FA variants, no existing device,
   pairing, recovery phrase, chat password, QR code, or additional prompt;
4. device revocation before/after prekey publication, claim, session
   establishment, archive grant, offline delivery, send commit, and
   acknowledgement, including stale offline devices and reconnect;
5. concurrent sends at the revocation/epoch boundary proving one complete
   current inventory, stable exact-byte retry, collision rejection, and no
   duplicate message, unread count, or notification;
6. old-key access to applicable retained history versus rejection from new
   epochs, plus each compromise row's future rotation set and non-retroactive
   limits;
7. logout, local and remote session expiry, authenticated emergency exit,
   browser/site-data clearing, storage denial, tab races, account deletion,
   backup/restore, and non-resurrection; and
8. accessibility 100, performance at least 95, CSP, unchanged interaction
   count, and capture-free synthetic evidence across the affected flows.

Instrumentation and artifacts must not contain passwords, plaintext, private
keys, prekeys, roots, ratchet state, archive keys, exact sensitive ciphertext,
authentication tokens, or recoverable browser storage.

## Unblocking and Review Sequence

1. Complete the earlier gate sequence, including pending G1 approval and a
   passing exact G2 protocol candidate.
2. Implement and accept G5, G8, and G9 on `codex/epic-2365`; readiness-only
   records do not satisfy any prerequisite.
3. Update `g10-readiness.json` to pin the accepted commits and transcribe the
   exact hierarchy, wrapping, membership, epoch, revocation, concurrency,
   cleanup, and deletion rules into failing tests.
4. Implement password/session preservation and compromise recovery with the
   smallest shared lifecycle coordinator, then produce every validation item
   above without adding a routine prompt or pairing dependency.
5. Obtain authentication/browser and independent security review at the exact
   implementation commit. Resolve blocking findings before enabling or
   claiming the lifecycle behavior.

The implementation author cannot fill either reviewer disposition. A recovery
claim is valid only for content created after every affected authority and key
scope has moved beyond the compromised material and stale clients are rejected.

## Consequences

- No unreviewed hierarchy, rewrap, reset recovery, revocation, epoch transition,
  stale-device exception, concurrency rule, or deletion behavior is introduced.
- Existing account access and classical chat history behavior remain intact.
- Password rewrapping and compromise recovery remain explicitly distinct, with
  old-key access and browser-erasure limitations recorded.
- Every acceptance criterion has an evidence slot rather than a fabricated
  prerequisite, browser result, cryptographic guarantee, or approval.
- G10 remains incomplete until G5, G8, and G9 pass and production integration,
  real-browser evidence, race/fault evidence, and human reviews exist.
