# Secure Case Builder MVP User Stories

Last updated: 2026-09-19

Linked issue: #2317

Parent epic: #2315

Prerequisite: #2320

## Status and Evidence Boundary

These are outcome-level draft stories for the Secure Case Builder MVP. They translate the issue's
named user needs and the accepted
[pre-build threat model](./SECURE-CASE-BUILDER-THREAT-MODEL.md) into a bounded backlog. They are not
implementation-ready workflow specifications.

The [source-workflow research memo](./SECURE-CASE-BUILDER-SOURCE-WORKFLOW.md) records that no
validated stakeholder workflow, categories, sequence, breakdowns, recovery language, or useful
output has been supplied. Those details remain blocked on the memo's completion gate. The stories
below must not be used to invent them. Until that evidence and the required product, content,
accessibility, and security reviews exist, a design may establish only the safety boundaries and
user outcomes described here.

The builder supports a person considering a disclosure; it does not determine whether the person
is a whistleblower, whether information is true, whether a case is strong, or what action the
person should take. It is not a legal, investigative, medical, employment, or emergency-response
service.

The [advisor and partner validation record](./SECURE-CASE-BUILDER-ADVISOR-VALIDATION.md) contains
no advisor or partner findings. Its public-information overlap assessment produced no accepted
scope change. The MVP remains provisional and must not be treated as validated until that record's
human-review and completion gates are satisfied.

## Successful MVP Outcomes

The MVP is successful when a user can reach any of these outcomes without being pushed toward
disclosure:

- continue working in the current open page;
- pause while keeping that page open;
- prepare a limited follow-up or audience-specific draft;
- independently explore an existing Hush Line recipient or attorney profile;
- explicitly share selected content through an available Hush Line account chat; or
- decide not to proceed, discard the visible draft, and leave.

Completion is not measured by how much a user enters, whether they contact anyone, or whether they
send a message. Skipping a prompt, removing content, pausing, and deciding not to proceed are all
valid outcomes. The MVP collects no product telemetry to distinguish or count them.

## MVP User Stories

All stories inherit the threat model's memory-only, no-telemetry, no-third-party-runtime, and
no-account-required editing boundary.

| ID        | Area                               | User story                                                                                                                                                                                                                                                            | Safety risk reduced                                                                                                            | MVP boundary                                                                                                                                                                                                                                                                                                                             |
| --------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SCB-US-01 | Pre-disclosure preparation         | As a person considering whether to disclose information, I want to understand the builder's device, retention, and sharing limits before I enter anything, so that I can decide whether to use it.                                                                    | Reduces unexpected device exposure, identity linkage, and loss of an unsaved draft.                                            | Show reviewed plain-language limits before entry and keep them available during use; make no promise of anonymity, confidentiality against device compromise, secure deletion, or legal protection.                                                                                                                                      |
| SCB-US-02 | Pre-disclosure preparation         | As a person preparing information, I want to add, revise, reorder, omit, and remove small pieces without following a mandatory sequence, so that I can work only with what is useful for my purpose.                                                                  | Reduces coerced completion, unnecessary disclosure, and loss of agency when the user's account does not fit a prescribed flow. | Work remains in the current page's memory. Exact categories, prompts, ordering, and recovery language require validated source-workflow evidence.                                                                                                                                                                                        |
| SCB-US-03 | Post-contact follow-up             | As a person who has already contacted someone, I want to prepare questions, clarifications, and new context separately from my earlier account, so that I can choose what a follow-up needs without automatically repeating everything.                               | Reduces context collapse and repeated or excessive disclosure.                                                                 | The user may revise follow-up material only in the open builder. The MVP does not import a prior message, link a draft to a case, or automatically send an update.                                                                                                                                                                       |
| SCB-US-04 | Evidence and corroboration mapping | As a person organizing what I already have, I want to show which information appears to support, conflict with, or leave uncertainty around another item, so that I can see gaps without the tool deciding credibility.                                               | Reduces false certainty, credibility scoring, and pressure to expose or obtain more information.                               | Mapping uses only user-entered references to material already available to the user. The builder must not ask the user to gather further evidence, verify allegations, upload source files, or produce an evidentiary or legal assessment. Exact labels and relationships require validated research.                                    |
| SCB-US-05 | Risk and uncertainty review        | As a person reviewing a possible disclosure, I want to mark what I am unsure about and review details that may identify or affect me or someone else, so that I can remove information that is not needed for my chosen next step.                                    | Reduces accidental identification, detriment to involved people, over-disclosure, and action based on implied certainty.       | The review is optional, neutral, and user-directed. It does not calculate risk, predict retaliation or outcomes, diagnose urgency, or recommend a course of action. Final prompts and labels require content and security review.                                                                                                        |
| SCB-US-06 | Narrative drafting                 | As a person preparing to communicate with a particular audience, I want to assemble and edit only the relevant pieces in an order I choose, so that I can make a focused draft without changing or disclosing the rest of my work.                                    | Reduces disclosure of irrelevant identifying detail and accidental reuse of one audience's context for another.                | Audience drafts exist only in memory and are not scored, generated, or treated as complete. Preset audiences, templates, and source-specific structures require stakeholder validation; the MVP must not generate legal arguments or advice.                                                                                             |
| SCB-US-07 | Continue or pause                  | As a person who needs more time, I want to continue or pause without being pressured to finish, so that I can stop when proceeding would feel unsafe or unhelpful.                                                                                                    | Reduces distress-driven disclosure and unsafe pressure to complete, while making accidental data loss less surprising.         | Continue and pause work only while the original page remains open. The interface must say that closing, reloading, navigating away, a crash, or power loss loses the draft; it must not create autosave, recovery, or background activity.                                                                                               |
| SCB-US-08 | Explore contacting counsel         | As a person considering counsel as one possible next step, I want to choose to explore existing attorney profiles separately, so that I can evaluate a recipient without the builder telling me that legal help is required or appropriate.                           | Reduces mistaken legal-advice framing, recipient impersonation risk, and unintended transfer of draft content.                 | The MVP may point to existing Hush Line discovery/profile surfaces without transferring builder content or claiming that a profile, verification signal, or communication creates privilege or protection. Contact remains a separate user-initiated flow.                                                                               |
| SCB-US-09 | Start Hush Line chat               | As a person who chooses to share through an available Hush Line account chat, I want to select individual items, inspect the exact assembled text and intended participant, and confirm the share twice, so that only content I knowingly approve leaves the builder. | Reduces overbroad disclosure, wrong-recipient disclosure, account-association surprises, and plaintext fallback.               | No item is preselected. Sharing requires an authenticated account, an available unlocked chat key, confirmed recipient/conversation identity, the existing signed and context-bound browser-side E2EE path, and a final warning. Canceling or any authentication, authorization, key, encryption, or network failure sends no plaintext. |
| SCB-US-10 | Decide not to proceed              | As a person who decides not to continue or contact anyone, I want to discard the visible draft and leave immediately without judgment, so that not disclosing is a safe and successful outcome.                                                                       | Reduces coercion, shame-driven disclosure, and exposure of content left visible in the page.                                   | Discard replaces sensitive rendered content and clears application references before leaving, without sending, saving, logging, or measuring the outcome. Copy must describe this as best-effort clearing, not secure erasure.                                                                                                           |

## Cross-Story MVP Acceptance Boundaries

Any later implementation of these stories must meet all of the following:

- Opening and editing the builder requires no account and creates no case identifier, server
  record, account lookup, or draft-specific request.
- Draft text, structure, labels, uncertainty, relationships, edits, and outcome choices remain out
  of URLs, browser and server storage, logs, analytics, error reports, notifications, and third
  parties.
- Reloading, restoring, navigating back or forward, closing, discarding, or reopening the route
  never restores a draft.
- No content is preselected for sharing, and every share shows the exact selected plaintext, the
  intended participant or conversation, the account and retention implications, and a cancel path
  before final confirmation.
- The existing account-chat E2EE, participant authorization, key-change handling, signing, and
  context binding are reused without a builder-specific plaintext endpoint or fallback.
- Warnings, relationships, ordering, all actions, and a non-spatial equivalent of any visual map
  are perceivable and operable with assistive technology and a keyboard, without relying on color
  alone.
- No flow rewards exhaustive disclosure, urgency, contact, or completion. The interface treats
  continue, pause, remove, discard, and decide not to proceed as neutral choices.
- Product language describes choices and technical limits. It does not judge credibility, advise
  on legal rights or strategy, predict safety or outcomes, or imply that using the builder creates
  confidentiality, privilege, or protection.

## Deferred User Stories

These needs are not part of the MVP. They remain user-perspective stories so a future proposal
must preserve the need and named risk rather than quietly broadening the MVP.

| ID       | User story                                                                                                                                                                                                  | Safety risk reduced                                                                                                                                                          | Why deferred / future gate                                                                                                                                                                                                                                                        |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SCB-D-01 | As a person who must close the page, I want to save and later resume a protected draft, so that I do not have to choose between losing work and keeping a sensitive page open.                              | Would reduce availability pressure, but a durable draft can expose case existence, content, identity, and access patterns.                                                   | Autosave, recovery, browser/server persistence, synchronization, accounts, and draft-key management are excluded from the MVP. Any proposal needs validated user need, a revised threat model, retention/deletion design, and security review.                                    |
| SCB-D-02 | As a person who chooses to keep or move a draft, I want to export it in a format and protection model I understand, so that I can use it outside the builder with an informed view of the resulting copies. | Would reduce unsafe ad hoc transcription, but generated files, keys, previews, backups, and deletion behavior can create durable exposure.                                   | The MVP has no download, export, print, clipboard, operating-system share, or generated-file flow. Export requires a documented need, client-side design, explicit warning and confirmation, and a new security review.                                                           |
| SCB-D-03 | As a person contacting counsel or another recipient, I want to transfer a reviewed draft into a supported contact channel, so that I do not have to re-enter selected information.                          | Would reduce transcription errors, but can expose content to the wrong recipient, channel, account, or retention regime.                                                     | The only MVP transfer is selected-content Hush Line account chat. Any handoff to public intake, email, an external service, or a counsel-specific flow requires recipient research, data-flow analysis, and security/content review; it must not imply legal advice or privilege. |
| SCB-D-04 | As a person with source material, I want to attach and relate documents or media, so that I can organize corroboration without reducing it to a note.                                                       | Would reduce loss of context, but files can reveal identity through content and metadata and can encourage risky evidence gathering.                                         | File intake, metadata handling, previews, storage, malware controls, and deletion are outside the MVP. Research must first establish the need, and the product must never ask a user to gather further evidence.                                                                  |
| SCB-D-05 | As a person writing for different audiences, I want reviewed templates or drafting assistance, so that I can adapt my account without guessing what each audience expects.                                  | Could reduce confusing or excessive narratives, but prescriptive or automated text can distort the user's meaning, expose plaintext, or be mistaken for professional advice. | Templates, automated rewriting, summarization, remote assistance, and audience-specific recommendations require validated source and recipient research, accessibility/content review, and a revised data-flow threat assessment.                                                 |
| SCB-D-06 | As a person seeking support, I want to collaborate on a draft with someone I choose, so that I can receive help without manually making uncontrolled copies.                                                | Could reduce accidental copying, but collaboration adds identity, authorization, key, metadata, revocation, and retention risks.                                             | Multi-user editing and sharing are excluded from the MVP and require evidence of need plus a new E2EE and abuse-case design review.                                                                                                                                               |

## Readiness and Review Gate

These stories can guide scope review now, but workflow design and implementation remain blocked
until:

- the source-workflow memo's stakeholder evidence and playback gates are complete;
- the exact categories, sequence, loops, exits, breakdowns, recovery behavior, useful outputs, and
  harmful prompts are traceable to that evidence rather than these stories;
- a maintainer/security reviewer accepts or revises the threat-model boundary;
- product, content, accessibility, and security reviewers approve the warnings and neutral choice
  language in context; and
- chat handoff design is reviewed against the implemented account-chat protocol and its current
  authentication, key-change, unlock, authorization, deletion, and metadata behavior.

If research shows that a useful workflow requires persistence, export, file handling, external
handoff, collaboration, or a different sharing boundary, that result changes the threat model; it
does not silently expand the MVP.
