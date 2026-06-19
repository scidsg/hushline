# Hush Line Two-Way Chat: End-to-End Encryption for Safer Disclosures

Last updated: 2026-06-18

## Abstract

Hush Line is an open source whistleblower platform built for secure,
privacy-preserving disclosures to journalists, lawyers, educators, organizers,
employers, boards, and other trusted recipients. Its original sender path is a
low-friction public tip form: a whistleblower can send a disclosure without
creating an account, and the recipient can triage it in a protected inbox.

Two-way chat adds an account-based follow-up channel for situations where a
logged-in sender and recipient both want to continue inside Hush Line. The
feature stores conversation messages as per-participant encrypted payloads,
requires signing-capable Hush Line chat keys for new replies, and keeps
conversation plaintext out of server-side storage. It does not replace anonymous
submissions. Instead, it gives users a second communication mode for cases where
ongoing account-based follow-up is appropriate.

This whitepaper explains the product motivation, security model, cryptographic
architecture, key lifecycle, operational boundaries, and known limitations of
Hush Line two-way chat.

## Executive Summary

Whistleblowing systems need more than secure intake. They also need usable
follow-up. Recipients often need clarifying details, sources need status and
next-step signals, and both sides need a workflow that does not force sensitive
communication into ordinary email, ad hoc messaging, or untrusted case notes.

Hush Line now supports two complementary paths:

- **Anonymous disclosure intake:** no sender account required, recipient PGP
  keys protect one-way submissions, and senders can return through a one-time
  reply/status link.
- **Two-way account conversations:** logged-in participants can continue
  follow-up in Hush Line with browser-based end-to-end encrypted conversation
  messages.

The two-way chat design has five core security goals:

- Store conversation content only as per-participant encrypted payloads.
- Restrict conversation routes to authenticated participants.
- Require signing-capable Hush Line chat keys for new replies.
- Bind encrypted envelopes to their intended conversation, sender, and
  recipient.
- Keep notifications generic so plaintext and ciphertext are not copied into
  email.

The feature improves follow-up usability without weakening the anonymous intake
flow. It also makes clear tradeoffs: account conversations expose operational
metadata to the Hush Line server, depend on trustworthy client code, and cannot
recover old chat history if a user loses the relevant chat key material.

## The Problem

Secure disclosure systems often focus on the first message. That first contact
matters, but many real cases do not end there. A recipient may need to ask for
dates, records, context, or corroborating details. A sender may need to learn
whether the recipient is reviewing the report, declining it, or waiting for more
information.

Without an integrated follow-up path, users tend to fall back to tools that are
easier but less appropriate for sensitive disclosures:

- ordinary email threads,
- consumer chat apps,
- screenshots and copied case notes,
- shared inboxes with unclear access boundaries, or
- one-off operational workarounds.

Those fallbacks can increase exposure for the sender and the recipient. They can
also fragment the evidence trail and make it harder for an organization to run a
consistent whistleblowing process.

Hush Line two-way chat is designed to keep follow-up close to the original
disclosure workflow while preserving the most important boundary: the server
should not need conversation plaintext to operate the product.

## Design Principles

Hush Line is safety-critical infrastructure for users whose operational,
physical, and digital security may be affected by software behavior. Two-way
chat follows the same principles used across the project:

- **Usability:** users must be able to complete the disclosure and follow-up
  workflow without specialist cryptographic knowledge.
- **Receiver authenticity:** senders need signals that they are reaching the
  intended person or organization.
- **Plausible deniability:** the system should avoid unnecessary artifacts that
  make sender participation more exposed than the selected workflow requires.
- **Availability:** disclosure intake must remain usable even when account chat
  is not the right path.
- **Anonymity:** anonymous submissions must remain available without requiring
  an account.
- **Confidentiality and integrity:** sensitive disclosure and conversation
  content should be protected against unnecessary server-side exposure and
  storage tampering.

These principles align with the ISO 37002 emphasis on trust, impartiality, and
protection in whistleblowing management systems. In practical product terms,
that means Hush Line must support communication without hiding critical limits
from users or operators.

## Two Complementary Communication Modes

Hush Line now distinguishes between anonymous one-way intake and account-based
conversation follow-up.

### Anonymous Intake

Anonymous intake remains the default sender-friendly path. A person can open a
public Hush Line profile, inspect trust signals, complete a structured form, and
submit a disclosure without creating an account. When message intake is enabled,
recipient PGP keys protect the submission content. The sender can receive a
one-time reply/status link after submission and return later to check progress.

This mode minimizes sender friction and avoids requiring an account where an
account would increase risk or reduce reporting likelihood.

### Account Conversations

Two-way account conversations are for logged-in Hush Line users. A logged-in
sender can submit to another account and continue follow-up in a conversation
thread when both sides have Hush Line chat keys.

This mode is useful when both participants accept the account-based model and
need ongoing follow-up inside Hush Line. It is not anonymous live chat. The
server must know enough metadata to show inbox rows, enforce participant access,
track unread state, and send generic notifications.

## Architecture Overview

Two-way chat uses browser-based cryptography and server-side participant
controls.

At a high level:

1. Each participant has a Hush Line chat key separate from their PGP key.
2. The browser encrypts conversation content for each participant.
3. The server stores per-participant encrypted copies.
4. Authenticated routes restrict conversation access to participants.
5. Participants unlock their chat key in the browser to read and reply.

The server stores conversation records, participant records, encrypted message
copies, timestamps, unread/activity state, and generic notification state. The
server does not store conversation plaintext.

Administrators can govern accounts, registration, directory trust states,
branding, and moderation settings. Admin status alone does not grant hidden
access to conversation content.

## Chat Keys and PGP Keys

Hush Line uses different keys for different jobs.

PGP keys protect one-way message intake, encrypted exports, and optional
encrypted notification email content. Proton Key Lookup helps users import
public PGP keys for those workflows.

Hush Line chat keys protect account conversation messages in the browser. They
are browser-generated in-app conversation keys and are separate from PGP keys.
Hush Line must not ask users to export, paste, or upload Proton Mail private
keys or any other external private key for chat.

New account conversation replies require active chat keys with public encryption
keys and public signing keys for every participant. Legacy unsigned envelopes
may remain readable for backward compatibility, but composing new replies is
unavailable until all participants have signing-capable chat keys.

## Conversation Creation

When a logged-in sender submits to another account and both sides are
chat-capable, the browser prepares encrypted initial conversation copies for the
sender and recipient. The initial conversation payload is bound to a one-time
nonce and participant key metadata before the server stores it.

This gives the sender a conversation thread tied to the submission while keeping
the plaintext in the browser. The recipient sees the conversation in the inbox
without a plaintext preview and unlocks their chat key to read it.

If chat setup is unavailable, Hush Line preserves the existing submission and
reply/status-link workflow when message intake is otherwise enabled.

## Reply Envelopes

Current reply envelopes use `ECDH-P256-AES-GCM` with versioned context binding.
Each encrypted copy is specific to one recipient participant.

Versioned envelopes include context for:

- the conversation,
- the sender participant,
- the recipient participant, and
- the envelope purpose.

That context is supplied as AES-GCM additional authenticated data and is covered
by signed envelope fields for signing-capable chat keys. This design helps
detect attempts to replay or swap ciphertext across conversations, sender
positions, or recipient positions.

The server validates structure, participant sets, context binding, and
signatures with the sender participant's registered public chat signing key
before storing new copies. The browser decrypts and handles signature-aware
message processing with the participant's unlocked chat key material.

## Notifications

Two-way chat notifications are intentionally generic. They tell a participant
there is new Hush Line conversation activity and instruct them to log in and
unlock their chat key.

Notifications do not include conversation plaintext or conversation ciphertext.
This remains true even when the user has enabled message-content notifications
for one-way tip intake.

Generic notifications reduce accidental leakage into SMTP logs, mailboxes,
forwarding rules, mobile lock screens, and third-party mail search indexes.

## Password Changes, Resets, and Recovery

Chat private key material must be available in the browser before a user can
read or reply to encrypted account conversations.

When a user changes their password and the active chat key is available, Hush
Line requires the key to be rewrapped in the browser as part of the password
change. This preserves access to existing chat history while changing account
credentials.

Password reset is different. If the old password is unavailable, Hush Line
cannot rewrap old chat key material. Old chat history encrypted to the previous
key remains locked unless a future recovery mechanism is explicitly designed,
reviewed, documented, and tested.

This is an intentional safety tradeoff. Server-side recovery would require a
new trust boundary and could become a plaintext access path if designed poorly.

## Security Properties

Two-way chat is designed to provide the following properties.

### Content Confidentiality at Rest

Conversation content is stored as encrypted copies for participants. The server
does not need plaintext to render the inbox, store messages, or send activity
notifications.

### Participant-Only Access

Conversation routes are authenticated and scoped to participants. A user who is
not part of the conversation should not be able to open the thread or append
messages.

### Context-Bound Integrity

Versioned encrypted envelopes bind ciphertext to conversation and participant
context. This limits replay and swapping attacks against stored conversation
copies.

### Signing-Capable Replies

New replies require signing-capable chat keys for all participants. This avoids
continuing legacy unsigned reply paths when the conversation cannot meet the
current integrity policy.

### Notification Minimization

Conversation notifications avoid both plaintext and ciphertext. They reveal
activity, not content.

## What the Server Still Knows

End-to-end encryption does not remove all metadata. Hush Line still stores and
processes operational information needed to run the feature, including:

- conversation participants,
- message and conversation IDs,
- timestamps,
- unread and activity state,
- message counts, and
- notification delivery state.

Users who need the lowest-account-footprint path should use anonymous
submissions and reply/status links instead of account conversations.

## Threats and Mitigations

### Unauthorized Conversation Access

An attacker may try to open a conversation they do not participate in. Hush Line
mitigates this with authenticated participant-scoped routes.

### Ciphertext Replay or Swapping

An attacker with database write access may try to move encrypted payloads across
threads or recipients. Versioned envelope context binding makes those payloads
specific to the expected conversation, sender, and recipient.

### Legacy Reply Policy Bypass

Legacy chat-key material may support reading older content, but new replies
require all participants to have signing-capable chat keys. The server and UI
must enforce the same availability policy.

### Chat Key Substitution

A compromised server or account may try to present a replacement chat key.
Fingerprints and signing-key metadata make key changes more visible, but Hush
Line does not yet provide a full key-transparency log. Users should treat
unexpected key changes as security-sensitive.

### Client-Side Code Compromise

Browser-based encryption depends on trustworthy JavaScript. A compromised
server, malicious deployment, or compromised build pipeline could serve code
that captures plaintext before encryption or after decryption. This remains a
critical residual risk for web-based end-to-end encryption systems.

### Metadata Exposure

The server sees account participation and activity metadata. Hush Line reduces
content exposure but does not make account conversations metadata-private.

## Operational Guidance

Operators and maintainers should treat two-way chat as a security-critical
workflow.

Before promoting the feature, verify:

- anonymous submissions still work without account creation;
- account conversations are available only to authenticated participants;
- new replies are unavailable unless every participant has signing-capable chat
  keys;
- inbox rows and notifications do not reveal conversation plaintext;
- password changes require chat-key rewrap;
- password resets leave old chat history locked to the old key;
- security headers and CSP remain enforced; and
- accessibility and performance targets remain intact.

Documentation, support materials, and launch copy should avoid saying that
two-way account conversations are anonymous. They are encrypted account
conversations for follow-up. Anonymous disclosures remain a separate flow.

## Limitations and Future Work

Hush Line two-way chat intentionally avoids server-side plaintext recovery, but
future work could improve usability and assurance without weakening that
boundary.

Potential areas include:

- clearer key-change warnings and user education,
- stronger key-transparency or contact-verification mechanisms,
- recovery designs that do not create hidden server access to plaintext,
- expanded independent security review of the browser cryptography and key
  lifecycle, and
- more public documentation for high-risk users choosing between anonymous
  reply links and account conversations.

Any future recovery or transparency mechanism should be reviewed as a
security-boundary change, documented in the threat model, and covered by tests.

## Conclusion

Hush Line two-way chat extends secure disclosure workflows from first contact to
ongoing follow-up. It gives logged-in participants an encrypted conversation
channel inside the product while preserving the anonymous no-account intake path
that remains central to Hush Line.

The feature is deliberately scoped. It protects conversation content from
routine server-side plaintext storage, binds encrypted replies to conversation
context, and keeps notifications generic. It does not hide all metadata, it does
not make account conversations anonymous, and it depends on trustworthy client
code.

Those limits are part of the security model. By documenting them directly, Hush
Line can launch two-way chat as a practical improvement to disclosure follow-up
without overstating what web-based end-to-end encryption can guarantee.

## References

- [Two-way chat end-to-end encryption](./TWO-WAY-CHAT-E2EE.md)
- [Use cases](./USE-CASES.md)
- [Threat model](./THREAT-MODEL.md)
- [Privacy policy](./PRIVACY.md)
- [ISO 37002 grounding document](./ISO-37002.md)
