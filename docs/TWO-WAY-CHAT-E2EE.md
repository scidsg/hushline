# Hush Line Two-Way Chat End-to-End Encryption

This document describes the product and security model for Hush Line two-way
account conversations. It is the implementation reference for launch materials,
library docs, and future whitepapers.

It is not a formal cryptographic proof. It explains the current design,
intended security properties, and limits that operators and reviewers should
understand before promoting the feature.

## Scope

Two-way chat is an account conversation feature for logged-in Hush Line users.
It lets a logged-in sender submit to another account and continue follow-up
inside Hush Line without relying only on the one-time anonymous reply link.

The existing anonymous disclosure flow remains the primary low-friction sender
path. Anonymous submissions still use the message inbox and reply/status link.
They do not create account conversations, and Hush Line must continue to support
users who cannot or should not create accounts.

## Goals

- Keep conversation plaintext out of server-side storage.
- Preserve participant-only access: only conversation participants can open or
  append to the conversation route.
- Require signing-capable Hush Line chat keys for new replies.
- Bind encrypted conversation envelopes to their intended conversation, sender,
  and recipient so stored ciphertext cannot be silently replayed across threads.
- Notify participants about new activity without copying conversation plaintext
  or ciphertext into email.
- Keep administrators outside the cryptographic trust boundary unless they are
  explicit conversation participants.

## Non-Goals

- Two-way chat is not anonymous live chat. Account conversations reveal account
  participation to the Hush Line server.
- Two-way chat does not hide operational metadata such as participants,
  timestamps, unread state, message counts, or recent activity.
- Two-way chat does not protect against malicious JavaScript served by a
  compromised application, build pipeline, or operator.
- Hush Line does not escrow chat private keys or provide server-side plaintext
  recovery for old chat history.

## Participant Requirements

New account conversation replies require every participant to have an active
Hush Line chat key with:

- a public encryption key,
- a public signing key, and
- unlockable private key material in the participant's browser session.

Hush Line chat keys are separate from PGP keys. PGP keys remain the mechanism
for encrypted one-way message intake, exports, and optional encrypted email
notification content. Proton Key Lookup imports public PGP keys only; it is not
used to import external private keys for chat.

## Conversation Flow

1. A user configures a Hush Line chat key in the browser.
2. A logged-in sender submits to another Hush Line account.
3. If the sender and recipient are chat-capable, the browser prepares encrypted
   initial conversation copies for both participants.
4. The server stores those encrypted copies and links the account conversation
   to the submitted message.
5. Each participant sees the conversation in the inbox without plaintext
   preview content.
6. A participant unlocks their Hush Line chat key in the browser to decrypt
   their copy and compose replies.
7. Replies are stored as per-participant encrypted payloads.
8. Other participants receive generic activity notifications and must log in and
   unlock their chat key to read the new message.

If chat setup is unavailable, the sender can still use the traditional
submission and reply-link workflow when message intake is otherwise enabled.

## Cryptographic Design

Conversation payloads are encrypted in the browser as structured envelopes.
Current reply envelopes use `ECDH-P256-AES-GCM` and versioned context binding.

Each encrypted copy is specific to one recipient participant. Versioned
conversation envelopes include context for:

- the conversation,
- the sender participant,
- the recipient participant, and
- the envelope purpose.

The context is supplied as additional authenticated data for AES-GCM and is
also covered by the signed envelope fields for signing-capable chat keys. This
helps prevent a database or storage attacker from replaying a valid ciphertext
into a different conversation, sender slot, or recipient slot without detection.

The server performs structural validation and participant/context checks before
storing copies. The browser performs plaintext decryption and signature-aware
message handling with the participant's unlocked chat key material.

## Key Lifecycle

Chat private key material is protected by the user's account password workflow
and must be available in the browser before reading or replying. Password
changes require the active chat key to be rewrapped in the browser before the
password is changed.

Password reset cannot rewrap old chat key material because the old password is
not available. After a reset, old chat history encrypted to the previous key
remains locked unless a future recovery mechanism is explicitly designed,
reviewed, documented, and tested.

Key rotation and old signing-key history support continuity checks for existing
conversation history. Legacy unsigned envelopes may remain readable for
backward compatibility, but new replies require signing-capable chat keys.

## Server-Side Data Handling

The server stores:

- conversation and participant records,
- per-participant encrypted message copies,
- timestamps and activity markers,
- unread/read cursor state, and
- generic notification state.

The server does not store conversation plaintext. Administrators can govern
accounts, directory trust states, registration, branding, and moderation
settings, but admin status alone does not grant conversation access.

Conversation notifications are generic. They do not include conversation
plaintext or conversation ciphertext, even when a user has enabled message
content notifications for one-way tip intake.

## Privacy and Security Properties

Two-way chat is designed to provide:

- **Confidentiality of conversation content at rest:** stored conversation
  payloads are encrypted per participant.
- **Conversation integrity checks:** versioned envelopes bind ciphertext to the
  expected conversation and participant context.
- **Receiver authenticity support:** public chat-key fingerprints and signing
  keys make key changes and envelope provenance more visible to participants.
- **Participant-only access:** authenticated routes are scoped to conversation
  participants.
- **Operational minimization:** notifications and inbox rows avoid plaintext
  previews.

These properties depend on users unlocking the correct chat key in a trustworthy
browser session and on Hush Line serving uncompromised client code.

## Residual Risks

- A compromised server or build pipeline can serve malicious JavaScript before
  encryption or after decryption.
- A database or operator can observe conversation metadata, including who is
  participating and when activity occurs.
- Account conversations require accounts and therefore have a different
  anonymity profile than anonymous submissions.
- Users who lose access to old chat key material can lose access to old chat
  history.
- Chat key substitution remains a serious attack if a participant ignores
  fingerprint changes or if a future key-transparency mechanism is not in place.

## Review Checklist

Before shipping conversation workflow changes, reviewers should verify:

- anonymous submissions still use the message inbox and reply/status link;
- conversations are available only to authenticated participants;
- replies are unavailable unless all participants have signing-capable chat
  keys;
- conversation rows and notifications do not reveal plaintext;
- password change still requires chat-key rewrap;
- password reset still locks old chat history encrypted to the old key; and
- accessibility remains 100 and performance remains at least 95 for affected
  pages.
