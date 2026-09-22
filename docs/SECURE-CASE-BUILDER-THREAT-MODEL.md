# Secure Case Builder Pre-Build Threat Model

Last updated: 2026-09-19

Linked issue: #2320

Parent epic: #2315

Prerequisite: #2319

## Status and Scope

Implementation update (2026-09-22): the maintainer-requested PDF and tip/self-send
workflows are covered by the [sharing boundary addendum](./CASE-BUILDER-SHARING-SECURITY.md).
That addendum supersedes the initial export deferral and chat-only sharing scope below.
The remaining browser/device, no-autosave, telemetry, and review requirements still apply.
This scope update does not represent an independent security review.

This document defines the security boundary and implementation constraints for the Secure Case
Builder before product implementation begins. It covers draft handling, browser and device risk,
metadata, telemetry, export, clipboard, print, screenshots, legal-process exposure, and an
explicit handoff into Hush Line account chat.

The source-workflow research remains incomplete. The
[research memo](./SECURE-CASE-BUILDER-SOURCE-WORKFLOW.md) contains no validated stakeholder
workflow, categories, sequence, or output. This threat model does not fill those evidence gaps or
authorize wireframes based on assumed findings.

In this document, **must** and **must not** are release-blocking security requirements. Any later
feature that crosses one of these boundaries requires an updated threat model and security review
before implementation.

## MVP Security Decisions

| Decision area           | MVP decision                                                            | Rationale                                                                     |
| ----------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Account                 | No account is required to open or use the builder                       | An account would create an unnecessary identity and activity link             |
| Processing              | Draft operations occur only in the current page's memory                | Keeps case plaintext out of Hush Line application and storage systems         |
| Persistence             | No autosave, recovery, synchronization, or browser/server draft storage | Browser storage creates a durable device artifact without a safe key boundary |
| Offline mode            | No installable app, service worker, or offline cache in the MVP         | Those mechanisms add retained code/data and misleading offline guarantees     |
| Telemetry               | No case-builder product telemetry                                       | Interaction data can reveal that a case exists or reconstruct its contents    |
| Export                  | No downloadable or generated-file export in the MVP                     | Files, temporary copies, backups, and deletion behavior need separate review  |
| Clipboard               | No copy button, clipboard read, or clipboard write in the MVP           | Clipboards can be retained, inspected, or synchronized across devices         |
| Print                   | No print control; printed case content is suppressed                    | Print queues, previews, and PDF workflows create uncontrolled copies          |
| Sharing                 | Only user-selected content may enter existing Hush Line account chat    | Reuses an established E2EE boundary and prevents whole-draft disclosure       |
| Builder encryption keys | The builder creates and stores no encryption keys                       | There is no retained draft to encrypt and no safe place to retain its key     |

"Local-only" means case content is not sent away from the page unless the user explicitly
confirms a chat share. It does not mean the web application is invisible to Hush Line, works from
a powered-off network, securely erases device memory, or is safe on a compromised device.

## Security Objectives

The MVP must:

- minimize collection and disclosure of case content and identifying context;
- preserve use without an account and avoid silently linking work to an account;
- prevent draft content, labels, and interaction history from reaching Hush Line servers,
  analytics, logs, URLs, or third parties;
- make every transition from local draft to shared content explicit and reversible until final
  confirmation;
- reuse, rather than fork or weaken, Hush Line's existing account-chat E2EE design;
- provide an immediate discard-and-leave path without saving; and
- state residual risks without promising anonymity, secure deletion, legal protection, or safety.

The MVP does not attempt to protect against a compromised browser, extension, operating system,
device, Hush Line client bundle, or person with physical or screen access. It is not a legal,
investigative, medical, emergency-response, or credibility-assessment tool.

## Assets and Sensitive Data

All case-builder state is sensitive, including apparently generic structure. Protected assets
include:

- draft text and any names, dates, locations, organizations, allegations, sources, or evidence it
  describes;
- categories, ordering, relationships, omissions, edits, and abandoned items;
- the existence, timing, duration, and frequency of a builder session;
- intended recipients and the subset selected for sharing;
- account, conversation, chat-key, and participant metadata used at the share boundary;
- any future exported, printed, copied, or screenshotted representation; and
- browser memory, form state, crash data, history, caches, and operating-system artifacts that can
  reveal the above.

Categories and interaction patterns can identify a person or matter even when names are removed.
They must receive the same handling as draft prose.

## Actors and Adversaries

Relevant actors include the person building a case, an intended Hush Line chat recipient, the Hush
Line operator, hosting and network providers, and people who later gain access through lawful
process or organizational policy.

Threat actors include:

- a person with casual or forensic access to the device;
- browser extensions, synchronized browser services, malware, assistive tools, or other local
  software with page access;
- a compromised or malicious Hush Line server, administrator, build pipeline, dependency, or
  client asset;
- a network observer able to correlate access timing, even though TLS protects content in transit;
- an unintended or impersonating chat recipient;
- a recipient who copies or redistributes shared plaintext; and
- a party compelling Hush Line, its providers, the user, or the recipient to produce retained
  records.

## Data Flow and Trust Boundaries

### 1. Initial page load

The browser requests a fixed builder route and its static assets over HTTPS or the configured onion
service. The request can expose ordinary access metadata such as time, source network information,
and route to infrastructure operators. The URL must not contain case state, identifiers, recipient
information, or analytics parameters. Loading the page must not create a case record or identifier.

An existing Hush Line session cookie may accompany a same-origin request even though an account is
not required. The builder must not read account data or condition editing behavior on account
state. Product copy must not claim that loading a same-origin builder is unlinkable from an
existing session or network identity.

### 2. In-memory editing

After the assets load, creating, editing, sorting, undoing, and deleting items must cause no network
requests. State exists only in JavaScript memory and the rendered document. It must not be placed
in cookies, URLs, history state, Web Storage, IndexedDB, Cache Storage, service workers, browser
databases, form-autofill stores, or server sessions.

### 3. Discard and navigation

The builder must offer an immediate discard-and-leave action. It must clear application references
and replace sensitive rendered content before navigation. Reload, back/forward navigation, tab
restoration, and reopening the route must not restore a draft. Page responses must use appropriate
`Cache-Control: no-store` behavior, and sensitive inputs must opt out of autocomplete where the
browser supports it.

Clearing the page is best-effort data minimization, not secure erasure. Operating-system memory,
swap, crash dumps, screen capture, and browser implementation details remain outside the app's
control. The interface must not say that a discarded draft is unrecoverable.

### 4. Explicit share to Hush Line chat

Sharing is a new trust boundary. It begins only after a user invokes share, selects individual
items, reviews the exact assembled plaintext, confirms the intended participant or conversation,
sees the safety warning, and confirms again.

The selected plaintext must pass directly to the existing browser-side account-chat encryption
implementation. Only its established versioned, signed, context-bound encrypted envelope may be
sent to the server. There must be no builder-specific plaintext endpoint, server-side encryption
fallback, hidden whole-draft field, or background sharing request.

If the user is not authenticated, the required chat key is locked or unavailable, a participant
key changed, recipient identity cannot be confirmed, or encryption fails, sharing must stop without
transmitting plaintext. Draft state must not be serialized into a redirect, server session,
browser storage, URL, or clipboard to bridge login or key unlock. Authentication may be completed
separately and sharing retried while the original page remains open.

After confirmation, the share is a copy. Later editing or discarding the local draft cannot remove
the recipient's conversation copy. Existing chat deletion semantics and server-visible metadata
remain unchanged.

### 5. Export, print, clipboard, and screenshots

The MVP has no application export, print, copy, operating-system share-sheet, or download flow.
Browsers and operating systems can still allow manual text selection, developer tools, extensions,
screenshots, screen recording, or external cameras. Hush Line must not claim to prevent these
actions or use invasive screenshot-detection techniques.

Print styles must suppress case content and provide a short explanation that printing from the
builder is unavailable. This reduces accidental copies; it does not prevent a determined user from
capturing what they can already see.

## Browser and Device Assumptions

The security design assumes a supported browser on a device the user currently controls, correct
TLS/onion configuration, and uncompromised production assets. Within that boundary:

- CSP, dependency controls, code review, and output encoding reduce script compromise but cannot
  make web-delivered client code trustworthy after a server or supply-chain compromise.
- Encryption cannot protect plaintext while the user is viewing or editing it.
- Browser private/incognito mode is not a security boundary and must not be recommended as a
  guarantee of no traces.
- Full-disk encryption and device access controls can reduce risk but are outside Hush Line's
  enforcement and must not be assumed.
- Screen readers and input methods necessarily receive content the user asks them to process;
  remote or cloud-backed assistive features can create an external disclosure path.
- Automatic spell-checking, translation, writing assistance, and browser/operating-system AI can
  transmit text. Sensitive fields must disable network-backed assistance where technically
  possible, while the interface explains that device configuration remains relevant.

## Threat Register

| Threat                                                      | Required control                                                                                                       | Residual risk                                                        |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Server stores or observes a draft                           | No draft API, case ID, server session state, or network request during editing                                         | Initial load and explicit share metadata remain visible              |
| Browser storage or recovery retains content                 | Memory-only state; no storage/service-worker APIs; no-store response; no restoration                                   | Browser, crash, swap, and forensic artifacts can remain              |
| XSS, dependency, or server compromise exfiltrates plaintext | Strict CSP, no third-party runtime, pinned/reviewed dependencies, safe rendering, and security-header regression tests | A compromised delivered client can read live plaintext               |
| Existing session links builder use to an account            | No account requirement or account lookup during editing; do not log cookies or builder identifiers                     | Same-origin/network logs can still permit correlation                |
| Telemetry reconstructs sensitive behavior                   | Zero builder product telemetry; no session replay, analytics SDK, event stream, or remote payload logging              | Baseline infrastructure logs reveal that the route was requested     |
| URL/history/referrer exposes state                          | Fixed URL with no state, recipient, or identifier in path, query, or fragment; `Referrer-Policy: no-referrer`          | Browser history can show that the builder route was visited          |
| Clipboard manager or synchronization retains plaintext      | No clipboard API or copy control; warn that manual copying leaves the builder boundary                                 | Native selection and external capture cannot be prevented            |
| Print/PDF/spooler creates durable copies                    | No print control; print stylesheet suppresses case content                                                             | Screen capture or external transcription remains possible            |
| Download/export creates recoverable files and backups       | Defer export entirely                                                                                                  | Users can manually recreate files outside Hush Line                  |
| Screenshot or shoulder surfing exposes content              | Concise persistent device-privacy guidance; no prevention claims or detection                                          | Anyone able to view the screen can capture it                        |
| Overbroad share discloses unnecessary details               | Item-level opt-in, exact preview, no select-all default, and a second confirmation                                     | A user can intentionally select identifying or excessive detail      |
| Wrong or substituted recipient receives content             | Show recipient/conversation identity and honor existing key-change/fingerprint warnings before encryption              | A compromised account or client can still misrepresent a recipient   |
| Share falls back to plaintext                               | Fail closed; use only existing client-side signed chat encryption; test every failure path                             | A compromised client can exfiltrate before encryption                |
| Authentication handoff persists the draft                   | Never put draft data in redirect state, sessions, storage, URLs, or clipboard                                          | An open tab still exposes live state on the device                   |
| Recipient or legal process obtains shared material          | Minimize the selected copy and explain recipient/server retention and metadata before confirmation                     | E2EE cannot control recipient plaintext or compelled endpoint access |
| Data loss harms availability or pressures unsafe disclosure | Explain before work begins that the MVP does not save; allow pause within the open tab                                 | Reload, crash, power loss, or eviction destroys the draft            |

## MVP Telemetry and Logging Policy

The MVP policy is **no product telemetry for the Secure Case Builder**.

Prohibited collection includes:

- draft content, derived summaries, categories, ordering, counts, lengths, and validation errors;
- clicks, keystrokes, edits, undo history, dwell time, completion, abandonment, or share selection;
- case, browser, device, installation, or pseudonymous identifiers created for the builder;
- session replay, heat maps, A/B testing, remote error payloads, or third-party analytics; and
- recipient selection, chat preview content, key material, or plaintext encryption failures.

Ordinary security and availability controls may record that the fixed route or an existing chat
endpoint was requested. Those records must follow the deployment's documented retention and access
policy and must not include request bodies, cookies, authorization values, URL state, full
referrers, case-derived dimensions, or builder-generated identifiers. Deployment-wide route
counts may be derived from sanitized logs only when they cannot be joined to a person, account,
session, case, or sequence of builder actions.

Production client errors must be handled locally with a generic user-visible error. Remote CSP or
error reporting must not be enabled for this surface unless a later review proves that payloads
cannot contain case text, DOM fragments, URLs, account/session identifiers, or interaction data.

## Safety Warnings

Warnings must be plain language, available to assistive technology, keyboard reachable, and not
communicated by color alone. They must appear at the decision point, not only in terms or help
pages. Final wording requires content and security review.

### Persistent builder notice

The editing surface must communicate that:

- work stays only in this open page and is not saved by Hush Line;
- closing, reloading, or leaving loses the draft;
- anyone or any software able to see the device or screen may see the content; and
- the user should include only what is needed for their chosen purpose.

It must not promise anonymity, confidentiality against device compromise, or secure deletion.

### Chat-share warning

Immediately before the final share confirmation, show:

- the exact selected content and intended participant or conversation;
- that the content will leave the local draft and the recipient can read and copy it;
- that Hush Line stores encrypted conversation copies plus server-visible participant, timing,
  unread/activity, and message-count metadata;
- that using account chat associates the share with the participating accounts;
- that discarding the builder draft will not delete a sent chat message or the recipient's copy;
  and
- that the user can cancel and return to editing without transmitting anything.

No item is preselected, and there is no one-click whole-case share.

### Future export warning and gate

Downloadable, printable, and clipboard exports are deferred. If a later proposal demonstrates a
validated user need, its updated threat model must cover file names and metadata, temporary files,
browser download history, previews, backups and cloud synchronization, encryption format and key
recovery, print queues, clipboard managers, cleanup, accessibility, and failure behavior.

Before creating any artifact, a future export flow must warn that it creates a copy outside Hush
Line's control; other people, applications, backups, administrators, or legal process may reach it;
deleting a file or emptying trash might not securely erase every copy; and encryption protects the
file only while its key and decrypted views remain protected. Generation must be entirely
client-side, initiated by an explicit confirmation, and must not upload plaintext or an export key.

## Encryption and Key Handling

Because the MVP does not persist drafts, adding local draft encryption would add key-management
risk without protecting live plaintext. The builder must not generate a draft key, derive one from
an account password, reuse a session secret, or label ordinary browser memory as "encrypted at
rest."

Chat sharing must use the current account-chat design documented in
[Two-way chat E2EE](./TWO-WAY-CHAT-E2EE.md): participant chat keys, client-side authenticated
encryption, signing-capable keys for new replies, versioned envelopes, and conversation/participant
context binding. The builder must not receive private keys, log unlocked key material, weaken key
change warnings, add a legacy unsigned path, or introduce server-side plaintext fallback.

TLS or onion transport remains required for initial assets and chat ciphertext but is not a
substitute for E2EE. A malicious delivered client can read a draft before encryption; the UI and
documentation must not claim otherwise.

## Legal Process and Retention Exposure

This is a data-location analysis, not legal advice or a promise about any jurisdiction.

| Holder or system                   | Information potentially available                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| Hush Line application and operator | Initial route access/security logs; after share, account/conversation metadata and ciphertext     |
| Hosting and network providers      | Connection, timing, routing, and other infrastructure metadata                                    |
| User's browser, device, or backups | Live draft, memory/device artifacts, screenshots, manually copied text, and any user-created file |
| Intended chat recipient            | Decrypted selected content, conversation context, and copies they create                          |

Content that Hush Line never receives cannot be produced from Hush Line's application database,
but local devices, providers, recipients, and metadata remain possible sources. E2EE limits
server-side access to message plaintext; it does not prevent compelled disclosure from an endpoint,
metadata production, account seizure, or a recipient voluntarily sharing content.

No interface copy may promise subpoena resistance, legal privilege, immunity, evidentiary status,
or deletion from every system. Jurisdiction-specific legal statements require review by qualified
counsel and are blocked until that review is recorded.

## Implementation Constraints and Verification Gates

Implementation stories must preserve all of these constraints:

1. The builder is usable without registration, login, or a server-created case object.
2. All draft state is ephemeral and memory-only; retained drafts, autosave, recovery, sync, and
   collaboration are out of scope.
3. Editing produces no network traffic. Runtime code and fonts/assets have no third-party
   dependency or connection.
4. The route uses the existing strict security headers with a minimally scoped CSP and adds no
   broader source. CSP regression coverage is required.
5. Case content never enters URLs, browser/server storage, logs, telemetry, error reports, or
   notifications.
6. Reload, restore, back/forward, discard, and exit behavior is tested to ensure the application
   does not restore a draft, while copy avoids claiming secure erasure.
7. Print rendering suppresses sensitive content, and the application exposes no download,
   export, clipboard, print, or operating-system share control.
8. Chat sharing sends only explicitly selected, previewed content through the existing E2EE path.
   Empty selection, canceled confirmation, locked/unavailable keys, authentication failure, key
   change, encryption error, and network error transmit no plaintext.
9. Share tests assert participant authorization, signed/context-bound envelopes, exact selection,
   no hidden whole-draft payload, warning accessibility, and unchanged CSP.
10. Server models, migrations, backups, administrative tools, and data exports gain no case-builder
    draft field or table.
11. Security tests inspect browser storage and network activity throughout editing and after exit.
12. Accessibility review covers non-visual ordering, warnings, keyboard-only operation, focus,
    reduced motion, zoom/reflow, and the non-spatial equivalent of any sorting interaction.

Any implementation that cannot meet a gate must stop for an explicit threat-model revision; it
must not quietly add persistence, plaintext fallback, broader CSP, or additional collection.

## Blockers and Required Review

The following remain blockers, not invitations to infer requirements:

- The source-stakeholder evidence and validation gates in issue #2319 remain incomplete, so the
  workflow, prompts, categories, order, and useful output cannot yet be implemented.
- A maintainer/security reviewer must accept or revise this MVP boundary before build stories are
  treated as ready.
- Product, content, accessibility, and security reviewers must approve the final persistent and
  share-warning copy in context before release.
- Sharing requires a design review against the implemented account-chat protocol and its current
  key-change, unlock, authorization, deletion, and metadata behavior.
- Export, saved drafts, multi-device sync, collaboration, installable/offline operation,
  clipboard helpers, and print output each require a documented need and a new security review.
- Any jurisdiction-specific legal-process or privilege language requires qualified legal review.

Within this boundary, the proposed MVP minimizes retained files and server knowledge. The largest
residual risks are the live browser/device, compromised delivered code, access metadata, and the
recipient endpoint after an intentional share. Those limits must remain visible to users and
reviewers throughout design and implementation.
