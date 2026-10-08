# Hush Line Use Cases

This document rationalizes Hush Line's use cases with [AGENTS.md](../AGENTS.md), the current application surface, and the public/library documentation.

The goal is to keep product thinking grounded in the people Hush Line actually serves, the workflows the app currently supports, and the safety/privacy constraints that shape those workflows.

## Grounding

- Primary grounding reference: `docs/ISO-37002.md`
- Product principles:
  - Usability of the Software
  - Authenticity of the Receiver
  - Plausible Deniability of the Whistleblower
  - Availability of the System
  - Anonymity of the Whistleblower
  - Confidentiality and Integrity of the Disclosures

## Primary User Groups

| Group                           | Typical Users                                                                                                                                                                              | What They Need From Hush Line                                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Message Senders                 | Whistleblowers, concerned citizens, engaged citizens, activists, students, bug bounty hunters                                                                                              | A low-friction, privacy-preserving way to find a trustworthy recipient and send a message without creating an account                              |
| Message Recipients              | Journalists, newsrooms, documentary teams, lawyers, law firms, employers, boards, educators, school administrators, organizers, activists, software developers, security teams, nonprofits | A trustworthy intake channel, secure delivery path, public credibility signals, and a manageable workflow for reviewing and responding to messages |
| Shared or Role-Based Recipients | Board inboxes, ethics/compliance contacts, public accountability channels, legal intake teams, security-reporting addresses                                                                | Shared intake endpoints that can be published publicly without forcing a single personal identity                                                  |
| Platform Administrators         | Internal operators for managed or single-tenant deployments                                                                                                                                | Branding, governance controls, registration gates, trust management, and account moderation                                                        |

## Deployment Models

| Model                                 | Best Fit                                                                               | Why                                                                      |
| ------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Managed SaaS                          | Most individual recipients and small teams                                             | Fastest path to a usable tip line with minimal operational overhead      |
| Managed PaaS / single-tenant instance | Organizations that need branding, registration control, or instance-level governance   | Supports tenant-specific settings and administrative controls            |
| Personal Server                       | Elevated-threat-model operators who want self-hosted, physically controlled deployment | Maximizes operational control for users with stronger adversary concerns |

## Directory and Discovery Patterns

The app and public directory support more than individual profiles. Current discovery patterns include:

- Individual tip lines for reporters, lawyers, educators, organizers, and security contacts
- Shared or role-based intake points such as board, ethics, compliance, or security-reporting inboxes
- Verified first-party Hush Line profiles
- Featured verified profiles promoted by instance administrators
- Imported public-interest directories for attorneys and newsrooms
- Imported SecureDrop and GlobaLeaks listings

## Core Flows by Access Level

| Access Level              | Core Flows                                                                                                                                                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unauthenticated users     | Browse directory, search verified recipients, search attorneys/newsrooms/imported sources, open a profile, submit a message, register, log in, complete 2FA challenge                                                                    |
| Authenticated users       | Finish onboarding, configure encryption, manage inbox, reply in account conversations, update statuses, resend or delete messages, edit profile, enable notifications, manage account security, use tools, download data, delete account |
| Authenticated paid users  | Upgrade, manage plan, add aliases, customize alias profiles, customize message-field intake beyond defaults                                                                                                                              |
| Authenticated admin users | Brand the instance, manage user guidance, control registration, verify accounts, apply caution/suspension states, grant admin, delete users or aliases                                                                                   |

## Detailed Use Cases

### Message Senders and Unauthenticated Visitors

| Actor            | I need to...                                                                   | So that...                                                                                               | Product Surface                                       |
| ---------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Whistleblower    | Find a credible recipient without creating an account                          | I can report quickly without procedural friction                                                         | Directory, profile pages                              |
| Whistleblower    | Search the directory by name                                                   | I can find a known person or organization directly                                                       | Directory search                                      |
| Whistleblower    | Filter recipients by trust or type                                             | I can narrow the list to verified accounts, attorneys, newsrooms, SecureDrop, GlobaLeaks, or all sources | Directory tabs and filters                            |
| Whistleblower    | See administrator-featured verified recipients first                           | I can quickly find the accounts this deployment most wants visitors to notice                            | Directory verified tab                                |
| Whistleblower    | Filter by geography                                                            | I can find a recipient relevant to my jurisdiction or risk environment                                   | Directory country/region filters                      |
| Whistleblower    | Inspect a public profile before I send anything                                | I can judge whether this tip line belongs to the right person or organization                            | `/to/<username>` profile page                         |
| Whistleblower    | See trust signals on a profile                                                 | I can reduce impersonation risk before contacting someone                                                | Verified badge, caution badge, linked profile details |
| Whistleblower    | Contact a recipient without signing up                                         | I can disclose information with less friction and less exposed identity surface                          | Public message form                                   |
| Whistleblower    | Submit from a trusted recipient website when embeds are enabled                | I can use the recipient's first-party contact page while Hush Line still controls the secure form        | Proposed hosted iframe embed                          |
| Whistleblower    | Submit structured information, not just a freeform note                        | I can answer the intake questions the recipient actually needs                                           | Default and custom message fields                     |
| Whistleblower    | Benefit from encrypted-by-default submission behavior where configured         | I can reduce exposure of the message contents in transit and at rest                                     | Public profile submission flow                        |
| Whistleblower    | Still complete a submission if client-side encryption payloads are unavailable | I do not lose the ability to report because of browser or JS constraints                                 | Server-side fallback handling                         |
| Whistleblower    | Receive a one-time reply link after submission                                 | I can return later without creating an account                                                           | Submission success page                               |
| Whistleblower    | Check the status of my tip later                                               | I can see whether the recipient is waiting, accepted, declined, or archived it                           | Public reply/status page                              |
| Visitor          | Register for an account when allowed                                           | I can become a recipient on the platform                                                                 | Registration flow                                     |
| Visitor          | Use an invite code when registrations are gated                                | I can still join approved deployments                                                                    | Registration with invite-code support                 |
| Visitor          | Complete a CAPTCHA during registration                                         | The platform can reduce low-effort automated abuse                                                       | Registration CAPTCHA                                  |
| Existing user    | Log in and complete a TOTP or enrolled security-key challenge                  | I can access my account securely without weakening accounts that already require MFA                     | Login and 2FA verification                            |
| Existing user    | Recover with an enrolled factor or recovery code                               | I can regain secure access without a server-side bypass                                                  | Login and authentication settings                     |
| Existing user    | Request password reset help without exposing whether my username exists        | I receive a generic response while Hush Line avoids treating notification recipients as recovery factors | Password reset flow                                   |
| Logged-in sender | Start an account conversation with another account after submitting a message  | I can follow up inside Hush Line without relying only on the one-time anonymous reply link               | Public message form, conversation page                |
| Logged-in sender | Unlock my Hush Line chat key in the browser before reading or replying         | Conversation plaintext stays out of server-side storage and is only decrypted in my browser              | Conversation page                                     |
| Logged-in sender | See when account conversation follow-up is unavailable                         | I do not mistake a legacy or unkeyed conversation for a safe two-way chat                                | Public message form, conversation page                |

### Authenticated Recipients: All Users

| Actor         | I need to...                                                                        | So that...                                                                                                | Product Surface                    |
| ------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| New recipient | Complete a guided setup flow                                                        | I can reach a minimally usable tip line quickly                                                           | Onboarding                         |
| New recipient | Skip onboarding and return later                                                    | I can get into the product without being trapped in setup                                                 | Onboarding skip                    |
| Recipient     | Add a display name                                                                  | Sources can recognize me by the name I use publicly                                                       | Settings -> Profile                |
| Recipient     | Add a short bio                                                                     | Sources understand why I am relevant and how to contact me safely                                         | Settings -> Profile                |
| Recipient     | Set an account category                                                             | I appear under a clearer recipient type                                                                   | Settings -> Profile                |
| Recipient     | Add my country, region, and city                                                    | Sources can find me by geography                                                                          | Settings -> Profile                |
| Recipient     | Add profile details like Signal, websites, social links, pronouns, or contact pages | Sources can verify me and choose a contact path with more confidence                                      | Settings -> Profile                |
| Recipient     | Get external profile links marked as verified when they link back with `rel="me"`   | Sources can see stronger authenticity signals                                                             | Profile-detail verification        |
| Recipient     | Opt in or out of the public directory                                               | I can choose whether I am discoverable in Hush Line search                                                | Settings -> Profile                |
| Recipient     | Add or update my PGP key manually                                                   | Submissions and exports can be encrypted for me                                                           | Settings -> Encryption             |
| Recipient     | Import my PGP key from Proton Mail                                                  | I can configure encryption without leaving the product workflow                                           | Proton key lookup                  |
| Recipient     | See that message intake is blocked until I have a PGP key                           | I do not publish a tip line that cannot safely receive content                                            | Public profile submission guard    |
| Recipient     | Enable email notifications                                                          | I can learn about new tips without watching the inbox constantly                                          | Settings -> Notifications          |
| Recipient     | Choose whether email alerts include message content                                 | I can balance convenience against data exposure                                                           | Settings -> Notifications          |
| Recipient     | Encrypt the full email body for compatibility with PGP-capable mail clients         | I can handle forwarded tips in clients like Proton Mail or Thunderbird                                    | Settings -> Notifications          |
| Recipient     | Configure custom SMTP forwarding                                                    | I can route notifications through approved infrastructure                                                 | Settings -> Notifications          |
| Recipient     | View all messages in one inbox                                                      | I can triage incoming reports                                                                             | Inbox                              |
| Recipient     | Filter my inbox by status                                                           | I can focus on the subset of cases I need to handle now                                                   | Inbox status filters               |
| Recipient     | Open an individual message                                                          | I can review the submission in full                                                                       | Message detail page                |
| Recipient     | Change a message status                                                             | The sender can see progress and next-step signals on the reply page                                       | Message status update              |
| Recipient     | Customize the public text for each status                                           | My workflow language can match my process and expectations                                                | Settings -> Message Statuses       |
| Recipient     | Resend a message to my email when notifications are enabled                         | I can re-enter my review flow without waiting for a new event                                             | Message resend                     |
| Recipient     | Delete a message                                                                    | I can remove data I no longer need to retain in the web UI                                                | Message delete                     |
| Recipient     | See account conversations in my inbox                                               | I can distinguish ongoing account follow-up from anonymous one-time tips                                  | Inbox conversation list            |
| Recipient     | Reply to an account sender after unlocking my chat key                              | I can ask follow-up questions without receiving plaintext on the server                                   | Conversation page                  |
| Recipient     | Delete my side of an account conversation                                           | I can remove an encrypted follow-up thread from my inbox without destroying another participant's history | Conversation action menu           |
| Recipient     | Receive only generic conversation email alerts                                      | Conversation ciphertext and plaintext are not copied into notification email                              | Conversation notifications         |
| Recipient     | Change my username                                                                  | I can correct or improve my published address                                                             | Settings -> Authentication         |
| Recipient     | Change my password                                                                  | I can recover from credential hygiene issues or rotation needs while rewrapping my active chat key        | Settings -> Authentication         |
| Recipient     | Enable 2FA                                                                          | My account is harder to take over                                                                         | Settings -> Authentication         |
| Recipient     | Enroll primary and separately stored backup security keys when rollout permits      | I can use an origin-bound factor without making one physical key my only recovery path                    | Settings -> Authentication         |
| Recipient     | Manage security keys after password-plus-factor confirmation                        | I can safely list, rename, or remove authenticators                                                       | Settings -> Authentication         |
| Recipient     | See when each security key was last used                                            | I can recognize stale or unexpected authenticators                                                        | Settings -> Authentication         |
| Recipient     | Remove an authenticator app while security keys remain                              | I can change factor types without silently disabling MFA                                                  | Settings -> Authentication         |
| Recipient     | Explicitly disable all MFA after strong reauthentication                            | I understand that my password becomes the only login protection and recovery codes stop working           | Settings -> Authentication         |
| Recipient     | Validate raw email headers                                                          | I can inspect whether a claimed email sender identity appears authentic                                   | Tools -> Email Validation          |
| Recipient     | Export an evidence ZIP from the email-header tool                                   | I can keep a portable artifact for later review or chain-of-custody work                                  | Email Validation evidence download |
| Recipient     | Use vision/OCR tooling on images                                                    | I can turn screenshots or photos into searchable text during case review                                  | Tools -> Vision Assistant          |
| Recipient     | Download my account data as a ZIP                                                   | I can back up, audit, or migrate my data                                                                  | Settings -> Advanced               |
| Recipient     | Encrypt my export with my PGP key                                                   | I can download a portable archive without weakening confidentiality                                       | Settings -> Advanced               |
| Recipient     | Delete my own account and related data                                              | I can exit the platform cleanly when needed                                                               | Settings -> Advanced               |

### Authenticated Recipients: Paid or Premium Flows

| Actor     | I need to...                                                              | So that...                                                                                                              | Product Surface                        |
| --------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Recipient | Choose a free or paid tier after onboarding when billing is enabled       | I can intentionally select the feature set I need                                                                       | Premium tier selection                 |
| Recipient | Upgrade to Super User                                                     | I can unlock higher-capability intake workflows                                                                         | Premium checkout                       |
| Recipient | View invoices and plan state                                              | I can understand my current billing status                                                                              | Premium dashboard                      |
| Recipient | Disable auto-renew                                                        | I can let a subscription end without immediate cancellation                                                             | Premium management                     |
| Recipient | Re-enable auto-renew                                                      | I can keep a plan active after previously scheduling cancellation                                                       | Premium management                     |
| Recipient | Cancel my subscription                                                    | I can return to the free tier intentionally                                                                             | Premium management                     |
| Recipient | Create additional aliases                                                 | I can operate matter-specific, campaign-specific, or role-based intake endpoints                                        | Settings -> Aliases                    |
| Recipient | Add multiple notification recipients with different addresses or PGP keys | A small organization can share one account while each operator keeps their own secure mail workflow                     | Settings -> Notifications              |
| Recipient | Give each alias its own display name, bio, and directory visibility       | Each intake endpoint can present the right public context                                                               | Alias settings                         |
| Recipient | Embed an opted-in profile or alias on a first-party website               | Paid Super Users can let senders submit from a website they already trust while Hush Line keeps the form and E2EE logic | Settings -> Developer / Alias settings |
| Recipient | Add custom message fields to my primary profile                           | I can tailor intake forms to my workflow instead of relying only on defaults                                            | Settings -> Profile -> Message Fields  |
| Recipient | Add custom message fields to aliases too                                  | Each alias can ask different intake questions                                                                           | Alias message fields                   |

### Administrators and Instance Operators

| Actor | I need to...                                                                                      | So that...                                                                                        | Product Surface             |
| ----- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | --------------------------- |
| Admin | Set directory intro text                                                                          | Visitors understand the purpose and scope of this deployment                                      | Settings -> Branding        |
| Admin | Set the primary color                                                                             | The instance can match organizational branding                                                    | Settings -> Branding        |
| Admin | Set the app name                                                                                  | The deployment can reflect the organization running it                                            | Settings -> Branding        |
| Admin | Upload or remove header and splash logos                                                          | The instance can use trusted visual identity markers                                              | Settings -> Branding        |
| Admin | Hide or show the donation button                                                                  | The deployment can control whether global fundraising UI appears                                  | Settings -> Branding        |
| Admin | Customize the profile header template                                                             | Public tip-line pages can use language that fits the deployment                                   | Settings -> Branding        |
| Admin | Set a specific homepage recipient                                                                 | The instance can land visitors on a named profile instead of the directory                        | Settings -> Branding        |
| Admin | Enable or disable embeddable profile forms                                                        | I can decide whether this deployment allows framed Hush Line intake on other sites                | Proposed embed controls     |
| Admin | Enable or disable user-guidance prompts                                                           | The deployment can decide whether to show safety guidance before disclosure                       | Settings -> User Guidance   |
| Admin | Customize emergency-exit text and destination                                                     | Visitors under local observation can leave quickly to a safer page                                | Settings -> User Guidance   |
| Admin | Add, edit, and delete guidance prompts                                                            | The deployment can tailor safety messaging to its users and jurisdictional context                | Settings -> User Guidance   |
| Admin | Enable or disable new registrations                                                               | I can control whether new accounts can join this deployment                                       | Settings -> Registration    |
| Admin | Pause security-key enrollment without ending enrolled-key authentication                          | I can stop rollout without silently downgrading factor security                                   | Deployment configuration    |
| Admin | Require registration codes                                                                        | I can gate participation to invited users                                                         | Settings -> Registration    |
| Admin | Create or delete invite codes                                                                     | I can administer gated sign-up without database access                                            | Settings -> Registration    |
| Admin | Search all usernames                                                                              | I can find accounts and aliases quickly in a larger deployment                                    | Settings -> Users           |
| Admin | See aggregate usage metrics such as user count, MFA adoption, PGP adoption, and chat-key creation | I can evaluate account-hardening posture and platform uptake                                      | Settings -> Metrics         |
| Admin | Submit encrypted administrative updates to eligible E2EE recipients                               | I can announce security workflow changes or new account-hardening features without weakening E2EE | Settings -> Broadcasts      |
| Admin | Resume an interrupted encrypted broadcast for pending recipients only                             | I can continue a large or interrupted announcement without duplicating delivered inbox messages   | Settings -> Broadcasts      |
| Admin | Mark a primary account or alias as verified                                                       | Visitors can see that a staff member verified the identity behind a tip line                      | Settings -> Users           |
| Admin | Mark one or more verified accounts as featured                                                    | Visitors see priority verified recipients at the top of the Verified directory tab                | Settings -> Users           |
| Admin | Mark an account as cautious                                                                       | Visitors can receive a visible warning before trusting a listing                                  | Settings -> Users           |
| Admin | Suspend an account                                                                                | The platform can stop new message intake for unsafe or abusive accounts                           | Settings -> Users           |
| Admin | Grant or remove admin privileges                                                                  | Governance tasks can be shared deliberately                                                       | Settings -> Users           |
| Admin | Delete a primary user account                                                                     | I can remove an account and its related data after active Stripe subscriptions are resolved       | Settings -> Users           |
| Admin | Delete an alias without deleting the whole user                                                   | I can remove an outdated intake endpoint while preserving the owner account                       | Settings -> Users           |
| Admin | Preserve participant-only access to account conversations                                         | Administrators can govern accounts without becoming hidden readers of conversation ciphertext     | Admin moderation boundaries |

## Two-Way Account Conversation Security Model

Two-way conversations are for logged-in Hush Line account holders who submit to another account while both sides can use Hush Line chat keys. Anonymous submissions continue to use the existing message inbox and reply-link flow; they do not create account conversations.

Hush Line chat keys are browser-generated in-app conversation keys. They are separate from PGP keys used for message intake, exports, and notification email compatibility. Proton Key Lookup imports public PGP keys only; Hush Line must not ask users to export, paste, or upload Proton Mail private keys or any other external private key for account conversations.

For the tested post-quantum OpenPGP recipient key profiles and deployment limits,
see [Post-quantum OpenPGP compatibility](POST-QUANTUM-OPENPGP.md). These profiles
do not change the algorithms used for in-app account conversations.

An unlocked Hush Line chat key remains available only in the authenticated browser tab's session storage so active conversations and page refreshes continue to work without another unlock. Hush Line clears that browser key material on logout, password reset, account deletion, or another explicit authentication cleanup; a changed server chat-key session identifier also prevents a stored key from being restored.

New account conversation replies require all participants to have active chat keys with public encryption keys and public signing keys. If any participant only has legacy chat-key material, the conversation remains readable where possible, but composing new replies is unavailable until all participants have signing-capable chat keys.

Conversation plaintext is not stored by the server. Conversation messages are stored as per-participant encrypted payloads, and only conversation participants can open the route or append replies. Administrators may manage accounts and trust states, but admin status alone does not grant conversation access.

Deleting an account conversation is local to the participant who deletes it. The conversation is removed from that participant's inbox, their encrypted copies are removed, and messages they authored appear as deleted placeholders to remaining participants. Other participants keep the thread and any encrypted copies still available to them. The shared conversation record is removed only after every participant has deleted their side. If the conversation began from a one-way intake message, that original message is detached or removed only when the shared conversation is fully removed.

Password changes require the active Hush Line chat key to be rewrapped in the browser before the password is changed. Password reset cannot rewrap an active chat key because the old password is unavailable; reset locks old chat history encrypted to that key. Old chat history remains unavailable unless a future recovery mechanism is explicitly designed, reviewed, documented, and tested.

Authentication recovery restores account access and permits replacement of lost factors, but does
not recover or unwrap encrypted chat history. Recovery-code generation requires recent strong
authentication, displays each high-entropy code only once, and invalidates prior sets. Codes are
stored only as hashes and consumed once. Password reset, notification email, support staff, and
administrators do not bypass an enrolled second factor.

Conversation notifications are generic activity alerts. They do not include conversation plaintext or conversation ciphertext, even when the recipient has enabled message-content notifications for one-way tip intake.

PR descriptions for conversation workflow changes should include a threat or risk summary, affected data paths, mitigations, validation commands, manual test steps, known risks, and follow-ups.

## Administrative Broadcast Resume Workflow

Administrative broadcasts create encrypted inbox messages in browser-side batches. Hush Line stores
a broadcast ledger with recipient status for each eligible recipient, but it does not store the
plaintext broadcast body. While the broadcast page remains open, transient batch submission failures
are retried automatically and committed batches can be replayed without duplicating delivered inbox
messages. If the browser or page stops after some batches are submitted, the next visit to Settings
-> Broadcasts shows the interrupted broadcast counts and limits the encryption audience to pending
recipients only. The admin must re-enter the same message, confirm the send, and continue only the
pending recipients because the server cannot recover unstored plaintext.

Resume validation must preserve two safety constraints:

- Same-page continuation may post the original audience and cumulative completed IDs while the
  server ledger has already moved earlier recipients out of pending status.
- Refresh-based continuation may post only the pending audience rendered by the resume page.

In both cases the server must reject new payloads for recipients that are no longer pending or no
longer eligible before creating additional messages, while acknowledging idempotent replays for
recipients already recorded as submitted or skipped. Pending recipients whose browser encryption
fails are recorded as skipped so the ledger can complete without duplicating successful deliveries.

## Manual Review Steps

Before merging conversation workflow changes, a human reviewer should:

- Log in as a sender with a Hush Line chat key, submit a message to another keyed account, and verify the sender lands on the conversation page.
- Log in as the recipient, open the inbox, verify the conversation row appears without plaintext preview content, unlock the chat key, and send a reply.
- Return as the sender, unlock the chat key, and verify the recipient reply is readable only after unlock.
- Submit an anonymous message to the same recipient and verify it still uses the reply-address success page and the legacy message row in the recipient inbox.
- Change a password with an active chat key and verify the rewrap step is required before the password change completes.
- Complete a password reset for an account with chat history and verify old chat history is locked until a new reviewed recovery mechanism exists.
- Inspect conversation and settings pages with the project accessibility and performance tooling; accessibility must remain 100 and performance must remain at least 95.

## Recurring Role-Based Scenarios

These scenarios come directly from `AGENTS.md`, the imported directory data, and the current app:

- Investigative reporter publishes a verified public tip line and adds website/social proof
- Newsroom publishes a shared intake profile and wants region-specific discovery
- Small newsroom, nonprofit, or legal intake team shares one account but routes notifications to multiple staff mailboxes with separate PGP keys
- Whistleblower law firm creates aliases for different matters or practice areas
- Board or ethics office maintains a role-based inbox instead of a single named individual
- Security team publishes a vulnerability-reporting tip line with tailored intake fields
- Educator or campus-adjacent trusted adult offers a safer contact path for students or families
- Advocacy organization uses a public-first-contact channel for harms, retaliation, detention, or abuse reports
- Elevated-threat-model operator prefers a self-hosted or tightly controlled deployment model

## Product Gaps This Document Should Continue Tracking

These are use-case themes already implied by the mission, even when the current implementation is partial:

- Shared multi-user handling of a single inbox beyond admin moderation
- Reporter acknowledgement and follow-up SLAs beyond public status text
- More explicit vulnerable-user accommodations in the sender flow
- Stronger evidence-review workflows that connect inbox, OCR, and authenticity checks more tightly
- Richer organizational case-management needs beyond status labels and inbox filtering

### Disposable Single Tenant provisioning test

An operator uses the app-style account and plan flow, confirms a simulated annual
payment, and enters a customer-controlled hostname. Confirmed payment authorizes
automatic provisioning without a customer deployment review. The isolated workflow
reads that order from private Git configuration and provisions a separate app and
database with staging-only credentials. One pre-deploy job initializes the schema
and private invitation before either app service starts, using lowercase boolean
configuration accepted by the app. The DNS screen displays the assigned CNAME
and ownership TXT records. Successful checks enable Continue without navigating;
the deployment screen separately verifies HTTPS and application health before its
own Continue action. A short-lived one-use invitation allows the operator to claim
the first administrator. This test is limited to one instance and does not implement
production billing or license enforcement. It uses a separate, order-scoped
Terraform root and workflow; shared staging and production workflows are unchanged.
Deployment refuses existing workspaces and cloud names, accepts only four resource
creations, and applies the exact checked plan. Cleanup requires the original order
manifest, recorded IDs, matching live cloud resources, and a checked saved deletion
plan. Recovery of the original test order can preserve its verified project and
database and repair its never-live failed app in place. Its exact app ID, hostname,
build branch, workspace, state lineage, and project membership must match; no
replacement, deletion, import, or database update is accepted. Fresh orders still
refuse every existing workspace. An incomplete apply or ownership mismatch stops
cleanup for operator review;
there is no unguarded scheduled or HCP automatic destruction. Remove the
`self-service-test` label on the controller PR to request guarded cleanup.

### Annual Single Tenant cancellation

A Single Tenant owner can cancel renewal while retaining service through the
prepaid annual period. The app shows the paid-through UTC date and asks the owner
to confirm permanent deletion of the instance and stored messages at that date.
There is no grace period. Cancellation can be withdrawn before expiry. Teardown
requires an authoritative annual billing record and exact tenant resource
ownership; an absent record or failed safeguard blocks deletion. The current
controller uses simulated payment terms and is restricted to the disposable test
instance; real checkout and production retirement policies remain separate work.

### Isolated full-lifecycle test

One new authorized disposable order uses a separate controller database and port.
The existing onboarding UI creates a simulated payment receipt, then a browser
provisioning action requests real, strictly isolated HushLineDev infrastructure.
A provider-assigned HTTPS hostname avoids any existing DNS changes. The fixture
has a complete synthetic calendar-year term ending approximately two hours after
checkout; its dates cannot be edited or rebound to another order. Cancellation
uses the existing owner-only acknowledgement and normal real-clock expiry worker.
A passing first attempt requires successful service deletion, refreshed empty
project deletion, confirmed provider absence and empty-workspace safe-delete,
with the original hushline.foo state unchanged. A failed or recovered attempt
does not count as uninterrupted success. The original controller and retired
fixture remain protected; real billing and production policies are unchanged.

### Account-bound Single Tenant subscriptions

Users create and authenticate a normal Hush Line account before choosing Free,
Super User, or Single Tenant. Single Tenant uses the existing UI framework and
requires a complete annual payment upfront. Pricing updates as the license count
changes; Unlimited licenses cost $20,000/year before infrastructure and the three
existing percentage charges. Verified Stripe payment authorizes provisioning.
Customers do not approve deployment reviews.

The account owns an opaque order reference. Only that account can monitor its
instance, obtain its private administrator invitation, or change renewal intent.
DNS verification and successful deployment checks never automatically advance
either Continue screen. Payment redirects alone do not authorize infrastructure. If the customer misses
the Checkout return, the payment-check action verifies the same owned session
without creating another payment or provisioning request. Live workflows obtain
fresh signed billing authority from the portal; Stripe keys remain there.

Cancelling renewal preserves service until the recorded paid-through date. At
that date the instance and stored messages are permanently deleted, with no
export grace period. Withdrawing cancellation preserves the same annual term.
Deleting the portal account retains a durable cancellation obligation separate
from the account. Pausing new Single Tenant sales never stops reconciliation.

The isolated launch rehearsal uses one reserved Stripe sandbox test clock and
provider-assigned HTTPS endpoint. It creates real infrastructure only after the
browser confirms sandbox payment and explicitly requests provisioning. Advancing
that owned clock changes neither the paid year nor shared UTC expiry rules.
Production activation remains a separately reviewed configuration change.

### Automatic paid instance operations

The general customer controller acknowledges a verified live annual payment into
a separate encrypted ledger before publishing an immutable signed Git request.
A healthy expiry worker and released default-branch workflows are required before
Checkout can accept a new purchase. The shared Linux controller requires its
dedicated mounted data volume and private service-user ownership; losing that
mount blocks ledger reads and writes without creating a replacement database. The cloud environment has no customer review
step; payment is independently rechecked before each guarded apply. Credentials
are verified against the explicitly configured HushLineDev team.

If a status callback is lost, the worker retrieves the original first-attempt
workflow's encrypted artifact and verifies its release, order, owner and request
revision. It does not repeat provisioning. Successful deployment checks remain
visible if a later check fails. Invitations are encrypted for the individual
order and become available only after ownership, DNS and HTTPS checks pass.

The billing worker independently rechecks expired terms to recover missed renewal
or cancellation webhooks. A paid renewal retains the same instance. An unpaid
year cannot extend service; a terminal cancelled subscription and the recorded
paid invoice authorize normal year-end deletion. Retirement records prevent later
callbacks or renewals from recreating a deleted instance. A fully verified
retirement releases the hostname for a new separately paid order; the original
order and payment tombstones remain permanent.

Updating production through the existing version-named infrastructure branch also
updates every active controller-managed instance to the version actually served
by production. The controller verifies the published release and queues a durable
per-order upgrade. Existing resources, encrypted runtime configuration and
administrator claims are retained; the initializer applies migrations. Each
workflow rechecks current payment and ownership, verifies exact signed source,
and reports success only for the matching active deployment. Upgrades never
restore a retiring instance or silently roll a database back. Failed upgrades
retain existing service state and require recorded operator recovery.

Customer workflow setup can use the approved development cloud and private-read
GitHub secrets directly. It never falls back to production cloud credentials or
repository signing keys; exact team, project, order and saved-plan guards remain
required before any provider mutation.

During installation, an operator can verify the approved development credentials
and dedicated customer project using the read-only default-branch preflight.
An ownership mismatch stops before querying infrastructure; a missing project
is reported without creating or adopting resources.

### Dedicated customer provider accounts

Single Tenant automation uses a separate DigitalOcean account and Terraform
organization, with explicit team and project IDs. Dedicated provider credentials
must be configured in the customer environment before it can accept orders.
The setup preflight rejects matching names with other IDs and cannot adopt or
modify production, staging, or another project's infrastructure.

### Immediate Single Tenant destruction and first-year registration code

An authenticated owner of a ready Single Tenant instance can choose **Cancel renewal and destroy my instance now** and explicitly acknowledge permanent deletion. The portal saves this irreversible intent before contacting Stripe, confirms cancellation of the owned live subscription without proration or an additional invoice, and queues exact-order teardown. Retries retain the same order and its recorded annual dates; the request cannot be withdrawn. The existing **Cancel renewal** option continues service until the annual term ends. Users must download anything they need before requesting destruction.

An explicitly configured live Stripe coupon may give one registration its first annual invoice at 99% off. It must be a 99% discount with `duration=once` and `max_redemptions=1`. All five annual price components and order ownership are still verified. Normal paid renewal resumes after the first year; unrelated, perpetual, sandbox, or unverified discounts do not authorize provisioning.

The trusted customer lifecycle container keeps its Python driver as the entrypoint. Workflow-supplied infrastructure and encrypted-result paths are driver arguments, so provisioning can start without treating a directory as an executable.
