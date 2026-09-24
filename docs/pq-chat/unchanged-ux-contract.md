# PQ Chat Unchanged-UX and Security Contract

Status: **Proposed for human approval**  
Decision gate: G1 of `scidsg/hushline#2365`

This is an implementation-independent contract. A later design may choose
algorithms, wire formats, key schedules, libraries, and migrations only after
showing that it satisfies every requirement here. “Must” and “must not” are
release gates. A deviation is a product/security decision, not an implementation
detail.

## Definitions

- **New copy:** any sender, recipient, archive, or other stored conversation
  content copy created after PQ chat activation for that conversation. Updating
  metadata without re-encrypting an older ciphertext does not turn it into a
  new copy.
- **Complete-copy PQ confidentiality:** every new content-bearing copy required
  for the supported two-party topology receives the approved hybrid protection.
  A sender self-copy, recipient copy, retry, migration copy, or server-held
  archive copy cannot be omitted from the claim.
- **Hybrid PQ confidentiality:** confidentiality is combined so that breaking
  only the classical component or only the approved PQ component is
  insufficient to recover content. Concatenating labels, merely offering both
  algorithms, or choosing either algorithm is not hybrid protection.
- **Normal path:** login (and existing 2FA where enabled), initial send, inbox,
  open/read, reply, refresh, and a fresh-browser login for an account that has
  not lost or reset its old secret.
- **Archive:** server-retained encrypted history intended to remain readable
  after ratchet/message keys are discarded. The term does not imply plaintext
  escrow.

## Security Claim Matrix

<!-- prettier-ignore -->
| Claim | Approved wording for a future implementation | Required evidence | Must not be claimed |
| --- | --- | --- | --- |
| Complete-copy confidentiality | Every new content-bearing copy in a PQ-enabled account conversation is protected by an approved classical+PQ hybrid. The write fails closed if any required copy cannot meet the contract. | Cross-implementation vectors; browser tests inspecting every initial/reply copy; server rejection tests for missing, mixed, malformed, replayed, or downgraded copies | “PQ chat” when only one participant copy, only transport, only key setup, or only one-way OpenPGP is PQ-protected |
| Downgrade behavior | There is no classical-only chat fallback for new copies after activation. Capability or encryption failure leaves account chat unavailable; the existing separate one-way PGP/anonymous flow may remain available under its own policy. | Negative capability, tamper, legacy-client, and partial-write tests | Silent classical fallback, mixed PQ/classical copies, or storing chat plaintext to preserve availability |
| Authentication | Content confidentiality is hybrid PQ. Account authentication, server-delivered key discovery, and current envelope authentication remain classical until a separately reviewed PQ-authentication design ships. | Protocol labels, UI/copy review, classical signature verification tests | “Post-quantum secure,” “quantum-safe authentication,” or protection against a quantum-capable active forger |
| Recorded-ciphertext attacker | A passive attacker who records a complete new hybrid ciphertext and later gains a cryptographically relevant quantum computer should still need to defeat the PQ confidentiality component. | Approved primitive/combiner analysis and vectors | Protection when the endpoint, unlock root, archive key, randomness, plaintext, or served JavaScript was compromised at encryption/decryption time |
| Archive compromise | Archive secrecy lasts only while the relevant archive secret remains secret. Compromise exposes every retained copy decryptable with that secret; rotation does not retroactively protect captured keys or ciphertext. | Key-scope tests, rotation/migration tests, backup/restore review | Ratchet forward secrecy for archive copies, retroactive repair, or safety after archive-root compromise |
| Ratchet compromise | A ratchet may limit past/future exposure only to the exact, tested key-erasure and post-compromise-recovery properties of the selected protocol. Archive copies remain governed by the archive row. | Protocol-specific state-compromise tests and analysis | Unqualified forward secrecy, post-compromise security, or secure deletion in a browser |
| Browser erasure | Hush Line performs best-effort removal from JavaScript references and browser storage on logout, reset, deletion, and session invalidation. | Storage/cleanup tests across supported browsers | Guaranteed erasure from memory, swap, crash reports, backups, extensions, screenshots, or forensic recovery |
| Served JavaScript | E2EE protects against routine server-side plaintext storage only while the browser receives trustworthy client code and keys. | CSP/supply-chain checks and threat-model review | Protection from a malicious server/build that serves code to capture plaintext or keys |
| Metadata | PQ content encryption does not hide account participation, timing, unread/activity state, message count, ciphertext size, or notification events from the service. | Data inventory and response tests | Anonymous or metadata-private account chat |
| Historical copies | Activation does not retroactively make existing classical ciphertext PQ-confidential. A migration may make a new hybrid copy only after explicit design, user availability, authenticity, and deletion semantics are reviewed. | Version/migration inventory | Relabeling or rewrapping without approved hybrid confidentiality as retroactive PQ protection |

## History Availability Contract

For a user who knows the current account password and has not taken a recovery
action that discards access to the old unlock root:

1. A normal login must make all retained, authorized conversation history
   available in a fresh supported browser.
2. The normal path must not require a new recovery phrase, hardware token,
   device-pairing ceremony, QR code, native app, browser extension, second
   device, or chat-specific password.
3. Existing account 2FA may remain part of login. It is not a new chat
   credential.
4. The login password may unlock or derive access to an account unlock root in
   the browser. The server must not receive conversation plaintext or an
   unwrapped content-decryption secret.
5. Same-tab refresh and supported same-session tabs should restore access
   without another prompt while matching unlocked state is available.

Password change with the old password must preserve history by rewrapping the
necessary secret in the browser and must retain current sibling-session
revocation behavior.

Password reset without the old password or another previously approved old
secret cannot recover the old unlock root. The current limitation is therefore
part of this contract: old encrypted chat history remains locked after reset.
A future recovery mechanism is a new trust boundary and must reopen product and
security review; it cannot be introduced as an implementation convenience.

## Everyday Workflow Contract

The PQ implementation must preserve these visible behaviors:

- Anonymous reporting remains account-free and separate from account chat.
- Login automatically unlocks or provisions chat when browser capabilities are
  available; conversation pages do not ask for a password.
- Initial profile submission keeps the existing fields, CAPTCHA, submit action,
  and success destination. It creates either all required hybrid copies or no
  account conversation.
- Opening the inbox does not display a plaintext preview. Opening a thread
  decrypts in the browser.
- Reply uses the existing composer and one send action. There is no “PQ mode”
  choice, algorithm picker, pairing gate, or per-message confirmation.
- Offline recipients receive only the existing generic activity notification
  and read the message after normal login.
- Alias profiles still resolve chat to the owner account; aliases do not become
  additional cryptographic participants.
- Participant-local conversation deletion, account deletion, and current data
  export scope remain as documented in the
  [baseline](baseline-flows.md#flow-checklist).
- Security or capability failure is explained accessibly and disables affected
  chat actions without exposing plaintext or weakening the algorithm.

## Measurable UX and Performance Budgets

These budgets are evaluated against the approved synthetic baseline on the same
runner class, browser build, production asset build, seeded data, network
profile, and message corpus. At least 30 measured runs are required for timing
percentiles; warm and cold results must be reported separately. Results are
engineering measurements, not user research.

<!-- prettier-ignore -->
| Surface | Budget / invariant | Release evidence |
| --- | --- | --- |
| Accessibility | Lighthouse accessibility score remains 100 on login, profile submission, inbox, and conversation pages; keyboard and live-status behavior remains usable | Lighthouse plus focused accessibility tests |
| Page performance | Lighthouse performance score remains at least 95 on the affected pages | Production-build Lighthouse report |
| Interaction count | Zero new required fields, credentials, prompts, confirmations, pages, or clicks in the normal path | Before/after Playwright trace and flow checklist |
| Login unlock | No second prompt. Added PQ work must not increase the baseline login-to-chat-ready p95 by more than 20% or 250 ms, whichever allowance is larger | Instrumented synthetic login in each supported browser |
| Initial send | One submit action. Added PQ work must not increase click-to-request-ready p95 by more than 20% or 250 ms, whichever allowance is larger | Instrumented synthetic profile submission |
| Reply send | One send action. Added PQ work must not increase submit-to-request-ready p95 by more than 20% or 250 ms, whichever allowance is larger | Instrumented synthetic reply for the maximum supported two-party payload |
| Thread open | No prompt after normal login. Added PQ work must not increase ciphertext-available-to-rendered-history p95 by more than 20% or 250 ms, whichever allowance is larger | Synthetic retained-history corpus, including the documented maximum supported history size |
| Main-thread responsiveness | No individual PQ chat task exceeds 50 ms without yielding, and no affected flow introduces a new long-task regression at p95 | Browser performance trace |
| Network writes | Initial send and reply remain atomic from the user's perspective; retries cannot duplicate visible messages, downgrade copies, or partially commit the required participant set | Request-count and idempotency/transaction tests |
| Payload limits | The chosen format, maximum plaintext size, and server ciphertext cap must be measured together before implementation approval; no implementation may silently truncate content | Boundary vectors and server/browser limit tests |

The 20%/250 ms allowance is a regression ceiling, not an expected cost or a
license to consume both. If a prototype cannot meet a budget, it must report
the measured result and trigger explicit reconsideration. It must not reduce
the test corpus, exclude a required copy, or weaken crypto to pass.

## Private Browsing and Storage Restrictions

The approved behavior is capability-based and fail-closed:

<!-- prettier-ignore -->
| Capability state | Required product behavior |
| --- | --- |
| Private browsing provides secure context, Web Crypto, required algorithm support, and tab storage | Full normal path is supported for that private session. Closing it discards unlocked browser state; the next fresh context uses normal login to recover retained history. |
| `sessionStorage` is writable | Same-tab navigation/refresh may restore the unlocked bundle, scoped to matching key and server chat-session identifiers. No unlocked key goes to persistent `localStorage`. |
| `sessionStorage` is blocked or quota-denied | The current document may operate with an in-memory key. The UI must not claim refresh persistence. If navigation loses the key, reading and sending disable safely; no classical/plaintext fallback is allowed. Normal login remains the recovery path. |
| `BroadcastChannel` is unavailable or partitioned | The unlocked tab continues to work. Another tab may remain locked; the product must not copy keys through server storage, URL parameters, or persistent local storage to compensate. |
| Required Web Crypto/PQ capability is unavailable | PQ account chat is unavailable with an accessible explanation. The anonymous one-way submission flow remains available when its existing requirements are met. |
| JavaScript is disabled | Account chat is unavailable. Existing server-side PGP fallback for one-way anonymous/profile intake remains separate and must not be described as PQ account chat. |

Private browsing is not promised to erase operating-system, browser, extension,
network, or service metadata. Storage restrictions are not permission to add a
new normal-path credential or weaken complete-copy PQ protection.

## Change Control

A later implementation PR must link each contract row to code, tests, and
measured evidence. Product and security reviewers must reconsider G1 before any
change that:

- adds a normal-path prompt, secret, pairing step, app, or extension;
- omits PQ protection from any new required copy;
- enables a classical-only or plaintext fallback;
- expands the participant topology or export contents;
- changes password reset recovery;
- claims protection from malicious served JavaScript or secure browser erasure;
- broadens the supported-browser claim without engine-specific evidence; or
- exceeds an approved budget.
