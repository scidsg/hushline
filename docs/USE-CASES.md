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
- Imported public-interest directories for attorneys and newsrooms
- Imported SecureDrop and GlobaLeaks listings

## Core Flows by Access Level

| Access Level              | Core Flows                                                                                                                                                                                               |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unauthenticated users     | Browse directory, search verified recipients, search attorneys/newsrooms/imported sources, open a profile, submit a message, register, log in, complete 2FA challenge                                    |
| Authenticated users       | Finish onboarding, configure encryption, manage inbox, update statuses, resend or delete messages, edit profile, enable notifications, manage account security, use tools, download data, delete account |
| Authenticated paid users  | Upgrade, manage plan, add aliases, customize alias profiles, customize message-field intake beyond defaults                                                                                              |
| Authenticated admin users | Brand the instance, manage user guidance, control registration, verify accounts, apply caution/suspension states, grant admin, delete users or aliases                                                   |

## Detailed Use Cases

### Message Senders and Unauthenticated Visitors

| Actor         | I need to...                                                                   | So that...                                                                                               | Product Surface                                       |
| ------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Whistleblower | Find a credible recipient without creating an account                          | I can report quickly without procedural friction                                                         | Directory, profile pages                              |
| Whistleblower | Search the directory by name                                                   | I can find a known person or organization directly                                                       | Directory search                                      |
| Whistleblower | Filter recipients by trust or type                                             | I can narrow the list to verified accounts, attorneys, newsrooms, SecureDrop, GlobaLeaks, or all sources | Directory tabs and filters                            |
| Whistleblower | Filter by geography                                                            | I can find a recipient relevant to my jurisdiction or risk environment                                   | Directory country/region filters                      |
| Whistleblower | Inspect a public profile before I send anything                                | I can judge whether this tip line belongs to the right person or organization                            | `/to/<username>` profile page                         |
| Whistleblower | See trust signals on a profile                                                 | I can reduce impersonation risk before contacting someone                                                | Verified badge, caution badge, linked profile details |
| Whistleblower | Contact a recipient without signing up                                         | I can disclose information with less friction and less exposed identity surface                          | Public message form                                   |
| Whistleblower | Submit structured information, not just a freeform note                        | I can answer the intake questions the recipient actually needs                                           | Default and custom message fields                     |
| Whistleblower | Benefit from encrypted-by-default submission behavior where configured         | I can reduce exposure of the message contents in transit and at rest                                     | Public profile submission flow                        |
| Whistleblower | Still complete a submission if client-side encryption payloads are unavailable | I do not lose the ability to report because of browser or JS constraints                                 | Server-side fallback handling                         |
| Whistleblower | Receive a one-time reply link after submission                                 | I can return later without creating an account                                                           | Submission success page                               |
| Whistleblower | Check the status of my tip later                                               | I can see whether the recipient is waiting, accepted, declined, or archived it                           | Public reply/status page                              |
| Visitor       | Register for an account when allowed                                           | I can become a recipient on the platform                                                                 | Registration flow                                     |
| Visitor       | Use an invite code when registrations are gated                                | I can still join approved deployments                                                                    | Registration with invite-code support                 |
| Visitor       | Complete a CAPTCHA during registration                                         | The platform can reduce low-effort automated abuse                                                       | Registration CAPTCHA                                  |
| Existing user | Log in and complete a TOTP challenge                                           | I can access my account securely                                                                         | Login and 2FA verification                            |

### Authenticated Recipients: All Users

| Actor         | I need to...                                                                        | So that...                                                                      | Product Surface                    |
| ------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------- |
| New recipient | Complete a guided setup flow                                                        | I can reach a minimally usable tip line quickly                                 | Onboarding                         |
| New recipient | Skip onboarding and return later                                                    | I can get into the product without being trapped in setup                       | Onboarding skip                    |
| Recipient     | Add a display name                                                                  | Sources can recognize me by the name I use publicly                             | Settings -> Profile                |
| Recipient     | Add a short bio                                                                     | Sources understand why I am relevant and how to contact me safely               | Settings -> Profile                |
| Recipient     | Set an account category                                                             | I appear under a clearer recipient type                                         | Settings -> Profile                |
| Recipient     | Add my country, region, and city                                                    | Sources can find me by geography                                                | Settings -> Profile                |
| Recipient     | Add profile details like Signal, websites, social links, pronouns, or contact pages | Sources can verify me and choose a contact path with more confidence            | Settings -> Profile                |
| Recipient     | Get external profile links marked as verified when they link back with `rel="me"`   | Sources can see stronger authenticity signals                                   | Profile-detail verification        |
| Recipient     | Opt in or out of the public directory                                               | I can choose whether I am discoverable in Hush Line search                      | Settings -> Profile                |
| Recipient     | Add or update my PGP key manually                                                   | Submissions and exports can be encrypted for me                                 | Settings -> Encryption             |
| Recipient     | Import my PGP key from Proton Mail                                                  | I can configure encryption without leaving the product workflow                 | Proton key lookup                  |
| Recipient     | See that message intake is blocked until I have a PGP key                           | I do not publish a tip line that cannot safely receive content                  | Public profile submission guard    |
| Recipient     | Enable email notifications                                                          | I can learn about new tips without watching the inbox constantly                | Settings -> Notifications          |
| Recipient     | Choose whether email alerts include message content                                 | I can balance convenience against data exposure                                 | Settings -> Notifications          |
| Recipient     | Encrypt the full email body for compatibility with PGP-capable mail clients         | I can handle forwarded tips in clients like Proton Mail or Thunderbird          | Settings -> Notifications          |
| Recipient     | Configure custom SMTP forwarding                                                    | I can route notifications through approved infrastructure                       | Settings -> Notifications          |
| Recipient     | View all messages in one inbox                                                      | I can triage incoming reports                                                   | Inbox                              |
| Recipient     | Filter my inbox by status                                                           | I can focus on the subset of cases I need to handle now                         | Inbox status filters               |
| Recipient     | Open an individual message                                                          | I can review the submission in full                                             | Message detail page                |
| Recipient     | Change a message status                                                             | The sender can see progress and next-step signals on the reply page             | Message status update              |
| Recipient     | Customize the public text for each status                                           | My workflow language can match my process and expectations                      | Settings -> Message Statuses       |
| Recipient     | Resend a message to my email when notifications are enabled                         | I can re-enter my review flow without waiting for a new event                   | Message resend                     |
| Recipient     | Delete a message                                                                    | I can remove data I no longer need to retain in the web UI                      | Message delete                     |
| Recipient     | Change my username                                                                  | I can correct or improve my published address                                   | Settings -> Authentication         |
| Recipient     | Change my password                                                                  | I can recover from credential hygiene issues or rotation needs                  | Settings -> Authentication         |
| Recipient     | Enable 2FA                                                                          | My account is harder to take over                                               | Settings -> Authentication         |
| Recipient     | Disable 2FA when necessary                                                          | I can recover from authenticator changes while staying in control of my account | Settings -> Authentication         |
| Recipient     | Validate raw email headers                                                          | I can inspect whether a claimed email sender identity appears authentic         | Tools -> Email Validation          |
| Recipient     | Export an evidence ZIP from the email-header tool                                   | I can keep a portable artifact for later review or chain-of-custody work        | Email Validation evidence download |
| Recipient     | Use vision/OCR tooling on images                                                    | I can turn screenshots or photos into searchable text during case review        | Tools -> Vision Assistant          |
| Recipient     | Download my account data as a ZIP                                                   | I can back up, audit, or migrate my data                                        | Settings -> Advanced               |
| Recipient     | Encrypt my export with my PGP key                                                   | I can download a portable archive without weakening confidentiality             | Settings -> Advanced               |
| Recipient     | Delete my own account and related data                                              | I can exit the platform cleanly when needed                                     | Settings -> Advanced               |

### Authenticated Recipients: Paid or Premium Flows

| Actor     | I need to...                                                              | So that...                                                                                          | Product Surface                       |
| --------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Recipient | Choose a free or paid tier after onboarding when billing is enabled       | I can intentionally select the feature set I need                                                   | Premium tier selection                |
| Recipient | Upgrade to Super User                                                     | I can unlock higher-capability intake workflows                                                     | Premium checkout                      |
| Recipient | View invoices and plan state                                              | I can understand my current billing status                                                          | Premium dashboard                     |
| Recipient | Disable auto-renew                                                        | I can let a subscription end without immediate cancellation                                         | Premium management                    |
| Recipient | Re-enable auto-renew                                                      | I can keep a plan active after previously scheduling cancellation                                   | Premium management                    |
| Recipient | Cancel my subscription                                                    | I can return to the free tier intentionally                                                         | Premium management                    |
| Recipient | Create additional aliases                                                 | I can operate matter-specific, campaign-specific, or role-based intake endpoints                    | Settings -> Aliases                   |
| Recipient | Add multiple notification recipients with different addresses or PGP keys | A small organization can share one account while each operator keeps their own secure mail workflow | Settings -> Notifications             |
| Recipient | Give each alias its own display name, bio, and directory visibility       | Each intake endpoint can present the right public context                                           | Alias settings                        |
| Recipient | Add custom message fields to my primary profile                           | I can tailor intake forms to my workflow instead of relying only on defaults                        | Settings -> Profile -> Message Fields |
| Recipient | Add custom message fields to aliases too                                  | Each alias can ask different intake questions                                                       | Alias message fields                  |

### Administrators and Instance Operators

| Actor | I need to...                                                                   | So that...                                                                         | Product Surface           |
| ----- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ------------------------- |
| Admin | Set directory intro text                                                       | Visitors understand the purpose and scope of this deployment                       | Settings -> Branding      |
| Admin | Set the primary color                                                          | The instance can match organizational branding                                     | Settings -> Branding      |
| Admin | Set the app name                                                               | The deployment can reflect the organization running it                             | Settings -> Branding      |
| Admin | Upload or remove a logo                                                        | The instance can use trusted visual identity markers                               | Settings -> Branding      |
| Admin | Hide or show the donation button                                               | The deployment can control whether global fundraising UI appears                   | Settings -> Branding      |
| Admin | Customize the profile header template                                          | Public tip-line pages can use language that fits the deployment                    | Settings -> Branding      |
| Admin | Set a specific homepage recipient                                              | The instance can land visitors on a named profile instead of the directory         | Settings -> Branding      |
| Admin | Enable or disable user-guidance prompts                                        | The deployment can decide whether to show safety guidance before disclosure        | Settings -> User Guidance |
| Admin | Customize emergency-exit text and destination                                  | Visitors under local observation can leave quickly to a safer page                 | Settings -> User Guidance |
| Admin | Add, edit, and delete guidance prompts                                         | The deployment can tailor safety messaging to its users and jurisdictional context | Settings -> User Guidance |
| Admin | Enable or disable new registrations                                            | I can control whether new accounts can join this deployment                        | Settings -> Registration  |
| Admin | Require registration codes                                                     | I can gate participation to invited users                                          | Settings -> Registration  |
| Admin | Create or delete invite codes                                                  | I can administer gated sign-up without database access                             | Settings -> Registration  |
| Admin | Search all usernames                                                           | I can find accounts and aliases quickly in a larger deployment                     | Settings -> Admin         |
| Admin | See aggregate usage metrics such as user count, 2FA adoption, and PGP adoption | I can evaluate account-hardening posture and platform uptake                       | Settings -> Admin         |
| Admin | Mark a primary account or alias as verified                                    | Visitors can see that a staff member verified the identity behind a tip line       | Settings -> Admin         |
| Admin | Mark an account as cautious                                                    | Visitors can receive a visible warning before trusting a listing                   | Settings -> Admin         |
| Admin | Suspend an account                                                             | The platform can stop new message intake for unsafe or abusive accounts            | Settings -> Admin         |
| Admin | Grant or remove admin privileges                                               | Governance tasks can be shared deliberately                                        | Settings -> Admin         |
| Admin | Delete a primary user account                                                  | I can remove an account and its related data when required                         | Settings -> Admin         |
| Admin | Delete an alias without deleting the whole user                                | I can remove an outdated intake endpoint while preserving the owner account        | Settings -> Admin         |

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
