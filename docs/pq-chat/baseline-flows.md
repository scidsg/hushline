# PQ Chat Baseline Flow and Evidence Checklist

Status: **Evidence for review; not a PQ implementation result**  
Baseline: Hush Line `v0.7.25` at commit `ab1d5ce3`  
Observed from repository state: 2026-09-24

This document records the current classical account-chat behavior that a PQ
design must preserve unless product and security reviewers explicitly reopen a
decision. The inspection used repository code, automated tests, and previously
committed screenshots made with synthetic development accounts. No real user
account, disclosure, browser session, or production service was used.

## Participant Topology

The supported account-chat topology is one conversation between exactly two
distinct authenticated primary user accounts: the submitting account and the
profile owner's account. Each message has one encrypted copy for each active
participant, including the author. An alias is an intake address owned by the
same recipient account; it does not create a separate participant, identity,
key owner, or group chat. Self-submission does not create an account
conversation.

Anonymous submitters are outside this topology. They use the one-way PGP inbox
and secret reply/status link. The server sees account-conversation membership,
timestamps, unread/activity state, message counts, and notification state.

Evidence:

- [`hushline/model/conversation.py`](../../hushline/model/conversation.py)
  defines per-user participants and per-participant encrypted copies.
- [`hushline/routes/profile.py`](../../hushline/routes/profile.py) creates the
  sender and recipient participants and rejects self-conversations.
- [`tests/test_profile.py`](../../tests/test_profile.py) covers primary,
  self-submission, anonymous, legacy-key, and alias submission paths.

## Flow Checklist

### Login and chat-key unlock

- [x] The normal username/password login remains the only chat unlock input.
- [x] With JavaScript and Web Crypto available, login creates a missing chat key
      or decrypts the existing wrapped chat key with the submitted account
      password. There is no separate conversation password or `Unlock Chat`
      prompt.
- [x] During a 2FA login, the password is retained only in page memory until the
      successful TOTP step, then used for the same automatic unlock.
- [x] If the browser path fails, ordinary account login can still complete, but
      chat stays locked. Failure does not expose private key material to the server
      or enable a weaker chat cipher.
- [x] Logout and explicit authentication cleanup clear in-memory and tab
      storage key material on a best-effort basis.

Evidence: [`assets/js/chat-key-lifecycle.js`](../../assets/js/chat-key-lifecycle.js),
[`tests/test_routes_auth.py`](../../tests/test_routes_auth.py),
[`tests/test_frontend_compat.py`](../../tests/test_frontend_compat.py), and
[`tests/test_2fa.py`](../../tests/test_2fa.py).

### Initial profile submission

- [x] An anonymous sender can submit without an account and receives the
      existing reply/status flow when one-way message intake is available.
- [x] A logged-in sender starts account chat only when the sender and recipient
      are distinct and both have active signing-capable chat keys.
- [x] The browser makes a sender copy and recipient copy. Both are bound to a
      single-use initial nonce and current key metadata; the server accepts the
      conversation only if the complete pair validates.
- [x] If account chat is unavailable, a PGP-capable profile retains the
      traditional one-way tip path. A profile with no usable PGP target and no
      valid chat payload rejects the submission rather than storing plaintext.
- [x] The public CAPTCHA and profile submission interaction are unchanged.

Evidence: [`tests/test_profile.py`](../../tests/test_profile.py), especially the
anonymous, logged-in, legacy-recipient, chat-only, nonce-replay, and alias cases;
and the synthetic browser test in
[`tests/playwright/e2ee/client-side-encryption.spec.js`](../../tests/playwright/e2ee/client-side-encryption.spec.js).

### Reply and live thread

- [x] A participant must authenticate, open a participant-scoped route, and
      have the correct unlocked key before plaintext renders or the composer is
      enabled.
- [x] Every reply is encrypted separately for all active participants and
      signed with the sender's current classical P-256 signing key.
- [x] The server checks structure, participant set, context, signature, CSRF,
      and write limits before persistence and notifications.
- [x] The browser never intentionally posts the reply plaintext. Polling and
      refresh replace encrypted page data and decrypt locally.
- [x] Legacy unsigned history can remain readable where possible, but a thread
      cannot accept new replies until all active participants have signing-capable
      keys.

Evidence: [`tests/test_conversation.py`](../../tests/test_conversation.py),
[`tests/test_frontend_compat.py`](../../tests/test_frontend_compat.py), and the
synthetic end-to-end browser lifecycle test in
[`tests/playwright/e2ee/client-side-encryption.spec.js`](../../tests/playwright/e2ee/client-side-encryption.spec.js).

### Offline recipient and notifications

- [x] An offline recipient's encrypted copy is stored and remains visible as an
      inbox conversation without a plaintext preview.
- [x] The recipient can later log in, unlock automatically, open the thread,
      and decrypt the copy.
- [x] Conversation email is a generic activity notice. It includes neither
      plaintext nor chat ciphertext, even if one-way message notifications are
      configured to include content.
- [x] Notifications are suppressed while the recipient has a recent active
      thread presence; a stale or offline recipient is notified.
- [x] Notification delivery failure does not roll back a stored encrypted
      message.

Evidence: notification and presence cases in
[`tests/test_conversation.py`](../../tests/test_conversation.py), inbox cases in
[`tests/test_inbox.py`](../../tests/test_inbox.py), and current notification
policy in [the E2EE reference](../TWO-WAY-CHAT-E2EE.md#server-side-data-handling).

### Fresh browser, refresh, and multiple tabs

- [x] A same-tab refresh restores the unlocked key from `sessionStorage` only
      when its key metadata and server-issued chat-key session identifier still
      match.
- [x] A second authenticated tab can request the key bundle from an unlocked
      tab through `BroadcastChannel`, scoped to the same chat-key session.
- [x] A fresh browser context has no stored plaintext key. Normal login uses the
      account password to unlock the server-stored wrapped chat key, so existing
      server-held ciphertext history becomes available without a new credential,
      pairing step, recovery code, or installed app.
- [x] Closing every tab or ending private browsing discards browser-held
      unlocked state from the application's perspective; the next login repeats
      the normal automatic unlock. This is not a secure-erasure claim.

Evidence: lifecycle storage and cross-tab assertions in
[`tests/test_frontend_compat.py`](../../tests/test_frontend_compat.py), automatic
login unlock in [`tests/test_chat_keys.py`](../../tests/test_chat_keys.py), and
the synthetic refresh exercised by
[`tests/playwright/e2ee/client-side-encryption.spec.js`](../../tests/playwright/e2ee/client-side-encryption.spec.js).

### Password change, reset, and account recovery

- [x] An authenticated password change rewraps the active chat private-key
      bundle in the browser before the server changes the password. Sibling account
      sessions are revoked.
- [x] A password reset does not possess the old password and cannot rewrap the
      old bundle. It marks the old chat key `password_reset_locked`, changes the
      chat-key session identifier, and leaves old history unavailable.
- [x] Notification addresses are not password-recovery authorities; the public
      reset request remains generic.
- [x] There is no server plaintext recovery or currently approved recovery path
      for history locked by reset without the old secret.

Evidence: [`tests/test_settings.py`](../../tests/test_settings.py),
[`tests/test_routes_auth.py`](../../tests/test_routes_auth.py), and
[the current key-lifecycle documentation](../TWO-WAY-CHAT-E2EE.md#key-lifecycle).

### Conversation deletion

- [x] Deleting a thread is participant-local. It removes that participant's
      access and copies plus copies of messages they authored, which appear as
      deleted placeholders for remaining participants.
- [x] Other participants retain their side until they also delete it. The
      shared conversation is removed after every participant deletes their side.
- [x] UI deletion and database deletion do not promise erasure from backups,
      replicas, browser memory, screenshots, notification metadata, or a copy
      already exfiltrated by a participant or attacker.

Evidence: deletion cases in
[`tests/test_conversation.py`](../../tests/test_conversation.py) and
[the current E2EE reference](../TWO-WAY-CHAT-E2EE.md#server-side-data-handling).

### Aliases

- [x] Alias profile fields and directory settings remain independent product
      surfaces, but account chat resolves to the alias owner's user account and
      chat key.
- [x] Deleting an alias does not delete its owner account. It is not a
      cryptographic participant revocation mechanism.

Evidence: alias submission in [`tests/test_profile.py`](../../tests/test_profile.py)
and alias lifecycle in [`tests/test_settings.py`](../../tests/test_settings.py).

### Account export and deletion

- [x] The current account export includes the account's user/profile/message
      tables and one-way PGP message files. It can wrap the ZIP to the account's PGP
      key.
- [x] The current export does **not** include conversation, participant, chat
      message, encrypted-copy, or chat-key tables. PQ work must not silently change
      that scope; adding portable chat history requires a separate product and
      security decision.
- [x] Account deletion removes the user and related information through current
      database relationships and clears browser key material on the submitted
      deletion form. It cannot retract plaintext or keys another participant or
      compromised client already obtained.

Evidence: [`hushline/settings/data_export.py`](../../hushline/settings/data_export.py),
[`tests/test_data_export.py`](../../tests/test_data_export.py),
[`hushline/settings/delete_account.py`](../../hushline/settings/delete_account.py),
and [`tests/test_delete_account.py`](../../tests/test_delete_account.py).

### Adjacent anonymous flow

- [x] Anonymous reporting requires no account or chat key.
- [x] Client-side OpenPGP encryption remains preferred, with the existing
      server-side PGP fallback when the client payload is unavailable.
- [x] Anonymous reply/status links remain secret bearer links and do not become
      account conversations.
- [x] PQ chat must not consume, replace, redirect, or add account prompts to
      this path. A chat failure must not become a plaintext fallback.

Evidence: anonymous submission cases in
[`tests/test_profile.py`](../../tests/test_profile.py), the browser encryption
test in
[`tests/playwright/e2ee/client-side-encryption.spec.js`](../../tests/playwright/e2ee/client-side-encryption.spec.js),
and [Hush Line use cases](../USE-CASES.md#message-senders-and-unauthenticated-visitors).

## Browser and Storage Support Baseline

The repository does not currently publish a multi-engine browser support
policy. The account-chat Playwright configuration selects Chromium. The
committed browser CI job also installs only Chromium, but currently runs the
separate one-way PQ OpenPGP spec rather than the account-chat lifecycle spec.
Desktop and mobile-sized Chromium screenshots are viewport coverage, not
evidence from distinct desktop/mobile browser engines.

This scope boundary is grounded in
[`playwright.e2ee.config.js`](../../playwright.e2ee.config.js) and the
[`pqc-browser` CI job](../../.github/workflows/tests.yml), both of which select
Chromium.

<!-- prettier-ignore -->
| Environment | Current evidence | Current behavior / claim limit |
| --- | --- | --- |
| Chromium, normal context | Executable Playwright account-chat lifecycle plus previously committed desktop/mobile-sized synthetic screenshots | Configured and artifact-backed baseline; no new result report in this packet |
| Firefox | No committed account-chat Playwright project | Unverified; no support claim from this packet |
| WebKit / Safari | No committed account-chat Playwright project | Unverified; no support claim from this packet |
| Private browsing with Web Crypto and working `sessionStorage` | Code-path inspection; no dedicated browser artifact | Expected to work within the private session; history returns through normal login after the private context closes |
| Storage restricted: `sessionStorage` throws | Explicit exception handling in lifecycle code | Current document can retain an in-memory key, but refresh restoration is unavailable; fail closed if the key is lost |
| `BroadcastChannel` unavailable | Explicit feature check in lifecycle code | Current tab works; automatic key transfer to another tab is unavailable |
| Web Crypto unavailable or insecure context | Explicit support checks | Account chat cannot encrypt/unlock and must fail closed; the separate anonymous one-way fallback remains governed by its existing policy |
| JavaScript disabled | Server login and one-way submission tests | Account chat is unavailable; anonymous one-way intake retains its existing server-side PGP fallback |

The proposed forward-looking support contract is in
[unchanged-ux-contract.md](unchanged-ux-contract.md#private-browsing-and-storage-restrictions).

## Synthetic Playwright Artifact Index

<!-- prettier-ignore -->
| Artifact | Synthetic actors | What it evidences | Limits |
| --- | --- | --- | --- |
| [`client-side-encryption.spec.js`](../../tests/playwright/e2ee/client-side-encryption.spec.js) | Seeded `artvandelay`, `not_newman`, and `admin` accounts; timestamped sentinel plaintext | Automatic login unlock, encrypted initial copies, two-party reply, offline recipient login/open, same-tab refresh, no plaintext in captured requests, rejection of malformed/context-tampered copies | Chromium only; executable test source, not a committed result report; does not exercise PQ chat |
| [Conversation/inbox screenshot manifest](../screenshots/releases/latest/README.md) | Seeded `artvandelay` and `newman` accounts from `scripts/dev_data.py` | Inbox and decrypted conversation presentation at desktop and mobile-sized viewports for both participants | Chromium capture; visual state only; captured 2026-06-20 |
| [Sender desktop thread](../screenshots/releases/latest/artvandelay/auth-artvandelay-conversation-thread-desktop-light-fold.png) and [mobile thread](../screenshots/releases/latest/artvandelay/auth-artvandelay-conversation-thread-mobile-light-fold.png) | `artvandelay` | Sender-side visible baseline | Previously committed artifact, not rerun for this packet |
| [Recipient desktop thread](../screenshots/releases/latest/newman/auth-newman-conversation-thread-desktop-light-fold.png) and [mobile thread](../screenshots/releases/latest/newman/auth-newman-conversation-thread-mobile-light-fold.png) | `newman` | Recipient-side visible baseline | Previously committed artifact, not rerun for this packet |
| [Conversation inbox](../screenshots/releases/latest/artvandelay/auth-artvandelay-inbox-conversations-desktop-light-fold.png) | `artvandelay` | Conversation row without message plaintext preview | Previously committed artifact, not rerun for this packet |

The existing one-way
[`pqc.spec.js`](../../tests/playwright/e2ee/pqc.spec.js) and
[Post-quantum OpenPGP report](../POST-QUANTUM-OPENPGP.md) validate PQ OpenPGP
recipient compatibility only. They are explicitly **not** PQ account-chat
evidence.
