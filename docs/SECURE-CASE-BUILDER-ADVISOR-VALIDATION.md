# Secure Case Builder Advisor and Partner Validation Record

Last updated: 2026-09-19

Linked issue: #2326

Parent epic: #2315

Prerequisite: #2316

## Validation Status

The [information architecture prototype](./SECURE-CASE-BUILDER-INFORMATION-ARCHITECTURE.md) is
available for review, but no advisor walkthrough, source-stakeholder playback, lived-experience
review, or partner discussion has been supplied or conducted. There are no sanitized participant
notes in the repository. Consequently:

- no advisor feedback or partner position can be reported;
- no prompt, label, sequence, referral, or collaboration boundary has been validated;
- no MVP scope change is accepted from this issue; and
- implementation remains blocked by the human review gates in this record and the prototype.

This record supplies a privacy-preserving fictional walkthrough, a common synthesis format, a
public-information overlap assessment, and a pre-implementation risk register. It does not turn
desk research or product-team hypotheses into stakeholder findings.

Use these evidence labels when this record is updated:

- `Observed`: behavior seen in a review session using fictional material.
- `Reported`: feedback stated by a participant.
- `Inferred`: a researcher's interpretation awaiting participant confirmation.
- `Public documentation`: a capability described by an organization's public material, not
  confirmed through a partner discussion.
- `Existing constraint`: a boundary already established by Hush Line or ISO 37002.
- `Open`: no evidence or decision is available.

## Review Cohorts and Evidence Availability

Names, contact details, schedules, raw notes, recordings, and real case details do not belong in
this repository. Record only role-level, sanitized findings after the participant has had an
opportunity to correct the synthesis.

| Review cohort                                                        | Perspective needed                                                                          | Evidence available         | Status                |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------- | --------------------- |
| Source stakeholder                                                   | Fidelity to the original sticky-note exercise, its recovery behavior, and its useful output | None                       | Blocked               |
| Issue-named advisor candidates (Erica and Balagi; roles unspecified) | Product, domain, or lived-experience critique without attributing sensitive details         | None                       | Not conducted         |
| Issue-named potential partner (Whistleblowers of America / Jackie)   | WRAP product overlap and collaboration, differentiation, or referral boundaries             | Public documentation only  | Partner position open |
| Lawyers and advocates                                                | Legal framing, privilege expectations, referral fit, and non-advice boundaries              | None                       | Not conducted         |
| Journalists                                                          | Source preparation, minimization, and recipient-workflow fit                                | None                       | Not conducted         |
| Clinicians                                                           | Trauma-aware language and clinical-boundary risks                                           | None                       | Not conducted         |
| Security and privacy experts                                         | Device, data-flow, metadata, E2EE, discard, and handoff risks                               | Existing threat model only | Human review open     |
| Whistleblowers with lived experience                                 | Agency, comprehension, emotional load, over-disclosure, and safe stopping                   | None                       | Not conducted         |

The named-advisor row reflects the candidate list in issue #2326 without assigning an
undocumented role, opinion, or affiliation to any person.

## Fictional Walkthrough Scenario

Use this scenario consistently so reviewers critique the proposed experience rather than disclose
their own or another person's case:

> Riley is a fictional employee of a fictional facilities contractor. Riley noticed that several
> safety inspections appeared as complete in an internal summary even though Riley did not see the
> inspections occur. Riley raised a question through an internal channel. Later, Riley's work
> schedule changed and Riley was left out of meetings, but Riley does not know why. Riley already
> has an ordinary calendar entry, a copy of the question they sent, and the summary they were
> authorized to access. Riley wants to organize what they remember, distinguish observations from
> assumptions, and decide whether to contact anyone. Riley does not want the tool to decide whether
> wrongdoing or retaliation occurred.

The scenario intentionally has uncertainty, possible identifying detail, existing material, and
no predetermined next action. Reviewers must not enrich it with a real employer, jurisdiction,
person, date, legal conclusion, diagnosis, or confidential source document. The walkthrough must
not ask Riley to obtain more evidence.

### Walkthrough tasks

Ask each reviewer to think aloud while completing these tasks against the low-fidelity prototype.
Do not explain the intended answer before observing the reviewer.

| Area               | Fictional task                                                                              | Observe and ask                                                                                                                                    |
| ------------------ | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Start / limits     | Decide whether Riley should enter the builder on this device                                | Which claims about privacy, loss, or safety are misunderstood? Does the warning support a free choice without creating panic or false reassurance? |
| Dashboard          | Choose where Riley would begin and identify anything that appears mandatory                 | Does the layout feel sequential, evaluative, or completion-driven despite the stated flat navigation?                                              |
| Notes              | Add Riley's observation, internal question, and later schedule change as separate pieces    | Is the expected size of a note clear? Can the reviewer skip, split, merge, revise, set aside, and recover without losing agency?                   |
| Provisional labels | Optionally distinguish an observation, context, impact, and an item to set aside            | Do labels imply truth, relevance, credibility, diagnosis, or legal materiality? Is leaving an item uncategorized genuinely workable?               |
| Claims             | Decide whether Riley should put anything here                                               | What does “claim” mean to the reviewer? Does the section imply a legal cause of action or pressure Riley to make an allegation?                    |
| Timeline           | Arrange the inspection summary, question, and schedule change without inventing exact dates | Can uncertainty and relative order be represented without adding identifying precision?                                                            |
| Evidence           | Describe only material Riley already has and relate it to another item                      | Does the flow pressure the reviewer to gather, upload, authenticate, or score evidence? Are “supports” and “conflicts” too conclusive?             |
| Risks & gaps       | Mark uncertainty and an identifying detail, then choose whether to keep it                  | Does “risk” imply a prediction? Does “gap” imply that Riley must collect or disclose more? What happens if imminent harm is mentioned?             |
| Narrative          | Assemble the smallest useful account for a reviewer-chosen audience                         | Can items be omitted without a completeness warning? Does editing a working copy have understandable consequences?                                 |
| Next action        | Compare continuing, pausing, exploring a recipient, sharing selected items, and stopping    | Is any outcome favored? Are page-loss, recipient, account, metadata, and post-send retention consequences understood?                              |
| Discard            | Stop without proceeding and leave the fictional draft behind                                | Does the confirmation delay a needed exit, shame the user, or promise secure erasure? What destination is expected?                                |

After the walkthrough, ask the reviewer to identify:

1. the first point of friction or confusion;
2. any prompt they would refuse or misread;
3. any information the prototype appears to demand unnecessarily;
4. any moment that could increase distress, retaliation risk, or exposure;
5. missing accessibility or non-spatial interaction needs;
6. the smallest useful output for Riley and its intended audience; and
7. the prompt, promise, judgment, or workflow the product must never include.

## Session Safety and Synthesis Protocol

- Use only the fictional scenario. Redirect personal accounts to an appropriate off-record support
  context and do not copy them into research notes.
- Do not record audio or video by default. Any separately approved recording needs informed
  consent, access controls, retention, and a deletion date before the session.
- Collect no participant contact data in the prototype and no case content in analytics, logs,
  screenshots, issue comments, or commits.
- Let a participant skip any task, pause, or end the session without explanation.
- Capture the workflow problem and role perspective, not identifying case context.
- Ask the participant to correct the sanitized synthesis before it informs a product decision.
- Report small samples as qualitative evidence. Do not publish participant counts or phrasing that
  could make a participant identifiable unless the research owner has approved a safe threshold.

Add validated feedback to the table below. One row may combine repeated feedback only when the
evidence label, cohort, and meaning remain accurate.

| ID  | Evidence label | Cohort | Prototype area | Sanitized feedback               | Friction or safety impact      | Proposed disposition | Participant-confirmed |
| --- | -------------- | ------ | -------------- | -------------------------------- | ------------------------------ | -------------------- | --------------------- |
| —   | Open           | —      | —              | No advisor feedback is available | Validation cannot be completed | Do not implement     | No                    |

## Public WRAP Overlap Assessment

This section is desk research, not partner feedback. It is based only on the
[Whistleblowers of America WRAP page](https://www.whistleblowersofamerica.org/learn-more/wrap-app),
reviewed 2026-09-19. Public content can change, and an implementation cannot establish the
organization's goals, technical behavior, research basis, accessibility, or willingness to
collaborate. Those points require direct confirmation.

| Area             | Publicly described WRAP approach                                                                        | Current Secure Case Builder boundary                                                                                                                    | Overlap / decision needed                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose          | Prepares a retaliation account before speaking with an attorney                                         | Supports neutral preparation before or after contact without choosing a recipient or outcome                                                            | Both organize a complex account; confirm whether their intended users and useful outputs are complementary or duplicative                             |
| Structure        | Five steps covering employment, complaint, and timeline                                                 | Flat, optional sections with no required sequence                                                                                                       | Both use structure; mandatory steps versus nonlinear use is a material differentiation requiring user validation                                      |
| Processing       | Says data stays in the browser and is lost on close or refresh                                          | Memory-only page state, no account required for editing, no persistence, and no telemetry                                                               | Strong technical-boundary overlap; compare actual data flows and wording with partner and security reviewers before making equivalence claims         |
| Output           | Reviews a summary and directs the user to print or save a PDF that may be emailed                       | No print, file export, clipboard action, email handoff, or external transfer in the MVP                                                                 | Output and referral paths diverge; do not add interoperability or a WRAP handoff without a new data-flow threat review                                |
| Evaluation       | Offers a paid severity analysis described as supporting legal-merit and clinical uses                   | No score, credibility assessment, diagnosis, legal sufficiency, or outcome prediction                                                                   | Deliberate differentiation; never imply Hush Line produces an equivalent assessment                                                                   |
| Device safety    | Warns users to keep the PDF safe and avoid a work computer                                              | Requires reviewed pre-entry and contextual device, visibility, loss, and residual-risk notices                                                          | Shared safety concern; partner review may reveal useful education, but Hush Line copy needs independent security, content, and accessibility approval |
| Contact boundary | Describes preparation before attorney contact and the possibility of emailing a PDF to the organization | Recipient exploration transfers no draft; the only proposed in-product transfer is explicit selected-content Hush Line account chat using existing E2EE | Referral or collaboration is undecided; no tracked link, endorsement, automatic transfer, or plaintext/email fallback is authorized                   |

### Provisional relationship boundaries

No collaboration, differentiation, or referral agreement exists. Until both organizations and
Hush Line's security and legal reviewers decide otherwise:

- **Collaboration:** limit discussion to research, safety language, and complementary user needs;
  exchange no case data and build no shared identifier or transfer path.
- **Differentiation:** keep Hush Line's broader, neutral, nonlinear preparation model separate from
  retaliation scoring, legal-merit support, diagnosis support, mandatory completion, and PDF/email
  output.
- **Referral:** do not recommend, rank, deep-link with tracking, prefill, or transfer content to
  WRAP. A future plain link still requires destination, endorsement, privacy, accessibility, and
  stale-content review.

## Pre-Implementation High-Risk Register

Every item below is flagged before implementation. `Blocked` means there is no authority to select
the prompt or behavior from this document.

| ID       | Prompt or workflow                                                    | Risk                                                                                                   | Required evidence or decision                                                                                  | Status      |
| -------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- | ----------- |
| VAL-R-01 | “Claims” and “core fact” labels                                       | Can imply legal classification, verified truth, or credibility                                         | Source/lived-experience research plus legal and content review                                                 | Blocked     |
| VAL-R-02 | “Supports,” “conflicts,” “evidence,” and “gaps”                       | Can pressure evidence gathering or imply sufficiency and investigative analysis                        | User validation plus legal, security, and content review; preserve ISO 37002's no-proactive-gathering boundary | Blocked     |
| VAL-R-03 | Timeline dates, locations, and ordering                               | Added precision can identify people or create false certainty                                          | Source and representative-user evidence plus privacy/content review                                            | Blocked     |
| VAL-R-04 | Risks, retaliation, crisis, or imminent-harm language                 | Can look like risk prediction, emergency monitoring, clinical advice, or a promise of protection       | Qualified security, legal, clinical/content, and lived-experience decision                                     | Blocked     |
| VAL-R-05 | “Pause” while keeping the page open                                   | Can hide loss risk or pressure a user to keep sensitive content visible                                | Usability and security review of warning comprehension and safer exit choices                                  | Blocked     |
| VAL-R-06 | Browser-only or “private” claims                                      | Can be read as protection from device compromise, network metadata, session linkage, or lawful process | Security-approved plain-language copy tested for comprehension                                                 | Blocked     |
| VAL-R-07 | Discard and leave                                                     | Can delay an emergency exit or promise forensic erasure                                                | Representative-user, security, accessibility, and content review of confirmation and destination               | Blocked     |
| VAL-R-08 | Recipient exploration or partner referral                             | Can imply endorsement, legal appropriateness, privilege, safety, or hidden tracking                    | Recipient and partner validation plus legal/privacy decision                                                   | Blocked     |
| VAL-R-09 | Selected-content account-chat handoff                                 | Wrong-recipient, account-linkage, key, metadata, retention, and plaintext-fallback risks               | Protocol-level security review and fail-closed tests against current Hush Line chat                            | Blocked     |
| VAL-R-10 | PDF, print, email, export, clipboard, or external handoff             | Creates durable, synchronized, misaddressed, or provider-accessible copies                             | Validated need and revised threat model, data flow, warnings, and security approval                            | Outside MVP |
| VAL-R-11 | Severity, completeness, credibility, legal-merit, or clinical scoring | Can distort decisions, diagnose, discriminate, or encourage excessive disclosure                       | Separate evidence, qualified review, and explicit governance; current product boundary prohibits it            | Outside MVP |
| VAL-R-12 | Real case examples in research or testing                             | Can expose whistleblowers, subjects, witnesses, strategy, and protected information                    | Use only sanitized fictional material under the session protocol                                               | Prohibited  |

## MVP Scope Disposition

There is no validated evidence supporting an addition, removal, or changed workflow. The MVP scope
therefore remains **unchanged and provisional**:

- retain memory-only, no-account-required editing with no persistence or product telemetry;
- retain optional, nonlinear movement and neutral continue, pause, share, and stop outcomes;
- retain descriptions of already-held material only, with no file intake or request to gather more;
- retain no scoring, automated conclusions, templates, professional advice, or claims of safety;
- retain no print, PDF, download, clipboard, email, external handoff, or partner integration;
- keep all labels, prompts, warnings, discard behavior, and the selected-content chat handoff
  blocked pending their named reviews.

This is a no-change disposition caused by missing evidence, not a finding that the proposed MVP is
usable, safe, wanted, or correctly differentiated. If validated feedback changes a workflow,
update the [source-workflow memo](./SECURE-CASE-BUILDER-SOURCE-WORKFLOW.md),
[threat model](./SECURE-CASE-BUILDER-THREAT-MODEL.md),
[MVP user stories](./SECURE-CASE-BUILDER-MVP-USER-STORIES.md), prototype, and
[`USE-CASES.md`](./USE-CASES.md) as applicable before implementation.

## Completion Gate

Issue #2326 can be treated as validated only when:

- the source stakeholder has approved a sanitized workflow synthesis and negative boundaries;
- representative advisor and lived-experience walkthrough findings are recorded above without
  sensitive details and participants have had a correction opportunity;
- Whistleblowers of America or another relevant partner has confirmed or corrected the overlap
  assessment and a named owner has decided collaboration, differentiation, and referral boundaries;
- every high-risk item has a named qualified reviewer and an accepted, revised, deferred, or
  prohibited disposition;
- the MVP scope documents record each change and its supporting evidence; and
- product, content, accessibility, legal, and security owners approve the resulting
  implementation boundary.

Missing evidence or a missing human decision keeps the affected prompt or workflow blocked. It is
not permission to infer feedback, silently retain a risky design, or begin implementation.
