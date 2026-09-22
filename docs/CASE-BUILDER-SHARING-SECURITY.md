# Case Builder sharing boundary

Updated: 2026-09-22. Parent epic: #2315; implementation PR: #2363.

This addendum records the maintainer-requested output workflows and supersedes the
export deferral and chat-only sharing scope in the
[pre-build threat model](./SECURE-CASE-BUILDER-THREAT-MODEL.md).
It does not waive independent security review or establish that the outstanding
source-workflow research has been completed.

## Reviewed content and local preparation

Draft notes, claims, timeline, evidence inventory, connections, and review markers
remain in page memory. There is no autosave or draft payload in URLs, browser storage,
analytics, or server logs. Only the explicitly reviewed narrative outline enters an
output action. Selecting sources and marking sensitive or excluded material does not
itself disclose those items. A changed outline invalidates its previous review.

## Password protected PDF

The browser generates a PDF with AES-256 revision 6 encryption, including encrypted
metadata, through pinned `@libpdf/core` 0.4.2. The user chooses and confirms a password
of at least 12 characters, limited to 127 UTF-8 bytes. The implementation does not
invent or retain a recovery password. It uses generic metadata and a generic filename.
Password fields are cleared after the export attempt and object URLs are revoked.
Missing font glyphs cause an explicit failure rather than silent content loss.

Export creates a durable copy outside the workspace. Its filename, download activity,
backups, opened plaintext, and any shared password can expose information. Encryption
does not protect an unlocked viewer, compromised browser/device, weak user password,
screenshots, or copies made after opening. Discarding the workspace cannot remove
these artifacts. There is still no automatic clipboard access or print action, and
browser printing suppresses workspace content.

## Send as a tip

A user action opens the directory in a new tab. The original page retains the reviewed
outline in memory for up to one hour. Transfer requires the exact opened window,
matching origin, and an allowed recipient path. The receiver validates the exact
opener and response source. The outline is not placed in a query string, fragment,
cookie, session storage, or local storage. The opener relationship is detached after
transfer, and the draft does not replace an already populated message field.

The recipient page shows the transferred text for review. Opening or populating this
page does not submit a tip. Final submission uses the existing intake encryption and
recipient checks. Account/directory visits still reveal ordinary connection metadata;
the builder does not promise invisible network activity or anonymity.

## Send to myself

An authenticated user opens their own tip page with the same review-before-submit
behavior. An unauthenticated user is directed through registration and login, then
saves the reviewed outline through the existing E2EE account-chat protocol. A PGP key
is not required for that new-account path.

The import endpoint requires authentication, CSRF protection, a session-bound import
identifier, and a signing-capable account chat key. It creates a one-participant
conversation and uses the existing signed ECDH-P256/AES-GCM envelope and message
validation. Plaintext remains in the browser; the server receives encrypted copies.
A locked, session-bound import deduplicates retries. Encryption failure leaves the
draft available for an explicit retry rather than sending plaintext. A secure browser
context is required for the existing client cryptography.

Saving links the encrypted conversation and ordinary message metadata to the new
account. It is deliberate persistence, unlike the otherwise unsaved builder. The
original workspace remains open. Login's pending import takes precedence over optional
onboarding; this does not mark onboarding complete or remove it from account navigation.

## Verification and residual risk

Browser checks cover memory-only editing, reload/history clearing, review gates,
chosen-password PDF export, exact new-tab payload transfer without submission,
new-account self-chat decryption, absence of plaintext in the chat request, and retry
deduplication. Server tests cover authentication, CSRF, import session binding,
signatures, encryption payload validation, and unchanged CSP restrictions.

The PR evidence uses invented data only. Independent PDF parsing verifies password
rejection, AES-256 revision 6, and preservation of the reviewed paragraphs; both PDF
pages are rendered for visual inspection. No CSP sources were added for these flows.
Compromised clients, physical access, recipient handling, account metadata, and exported
copies remain outside the protection offered by an in-memory workspace.
