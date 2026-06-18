# Two-Way Conversations

Source basis: Hush Line account conversation behavior and
[Two-way chat end-to-end encryption](../../TWO-WAY-CHAT-E2EE.md).

Two-way conversations let logged-in Hush Line account holders continue follow-up
inside Hush Line after a logged-in sender submits to another account.

They are different from anonymous one-time reply links. Anonymous submissions
still use the normal message inbox and reply/status page, and they do not
require the sender to create an account.

## When conversations are available

Conversations are available when both sides are logged-in Hush Line accounts and
all participants have active, signing-capable Hush Line chat keys.

A Hush Line chat key is separate from your PGP key:

- PGP keys protect one-way tip intake, exports, and optional encrypted email
  notification content.
- Hush Line chat keys protect account conversation messages in the browser.

If a participant only has older chat-key material or has not finished chat setup,
Hush Line may still show existing conversation history where possible, but new
replies are unavailable until every participant has signing-capable chat keys.

## Reading and replying

1. Open the conversation from your inbox.
2. Unlock your Hush Line chat key in the browser.
3. Read the decrypted conversation content locally.
4. Send replies only after the composer is available.

Hush Line stores conversation messages as encrypted copies for each participant.
The server does not store conversation plaintext.

## Notifications

Conversation notification emails are generic activity alerts. They tell you to
log in and unlock your chat key, but they do not include conversation plaintext
or conversation ciphertext.

This is true even if you have enabled message-content notifications for one-way
tip intake.

## What conversations do not hide

Two-way account conversations are not the same as anonymous submissions. The
server still needs operational metadata such as participants, timestamps, unread
state, and recent activity to show the inbox and send notifications.

For the lowest-friction anonymous sender path, continue using the standard
public tip form and reply/status link.
