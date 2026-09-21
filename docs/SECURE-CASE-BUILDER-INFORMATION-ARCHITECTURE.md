# Secure Case Builder Information Architecture Prototype

Last updated: 2026-09-19

Linked issue: #2316

Parent epic: #2315

Prerequisite: #2325

## Prototype Status

This document is a low-fidelity, non-interactive prototype of the sections named in issue #2316.
It establishes a navigation hypothesis, empty states, safety boundaries, and exit paths for review.
It does not authorize product implementation.

The [source-workflow research memo](./SECURE-CASE-BUILDER-SOURCE-WORKFLOW.md) has no validated
stakeholder categories, sequence, prompts, breakdowns, recovery language, or useful output. The
section names in this prototype therefore come only from issue #2316. Labels and example copy
inside the sections are hypotheses marked for research and review, not findings about the
sticky-note exercise.

The prototype inherits the memory-only boundary in the
[pre-build threat model](./SECURE-CASE-BUILDER-THREAT-MODEL.md) and the neutral outcomes in the
[MVP user stories](./SECURE-CASE-BUILDER-MVP-USER-STORIES.md). It adds no similar-case or legal
library; that component is deferred by the
[case-education library recommendation](./SECURE-CASE-BUILDER-CASE-EDUCATION-LIBRARY.md).

## Annotation Legend

- `[RESEARCH]`: source-stakeholder evidence is required before the choice can be accepted.
- `[CONTENT]`: content-design review is required for comprehension, tone, and pressure.
- `[SECURITY]`: security/privacy review is required before implementation.
- `[LEGAL]`: qualified legal review is required before release.
- `[A11Y]`: accessibility review and usability testing are required.

Every bracketed item remains unresolved. The annotations are omitted inside repeated wireframe
chrome for readability but apply wherever the same element appears.

## Proposed Information Architecture

The builder is one flat workspace rather than a required sequence. A user may open any section
from the dashboard or global navigation and may move between sections in any order.

```text
Start / limits
      |
      v
+------------------------------------------------------------------+
| Dashboard                                                        |
|                                                                  |
|  Notes <------> Claims <------> Timeline <------> Evidence        |
|    ^              ^                ^                ^             |
|    +--------------+----------------+----------------+             |
|                   |                                              |
|              Risks & gaps <------> Narrative                      |
|                   ^                    ^                          |
|                   +--------------------+                          |
|                              |                                   |
|                              v                                   |
|                   Share plan / next action                       |
+------------------------------------------------------------------+
      |
      +----> Continue or pause in this open page
      +----> Explore a recipient separately (no draft transfer)
      +----> Share selected items in available account chat
      +----> Discard visible draft and leave
```

The arrows show allowed movement, not a recommended order. Dashboard cards never show completion
percentages, urgency, scores, or a preferred next section. The builder does not use “steps,”
“required,” or “complete your case” language. `[CONTENT] [RESEARCH]`

### Global shell

```text
+------------------------------------------------------------------------+
| Hush Line | Secure Case Builder                         [Discard & leave]|
+------------------------------------------------------------------------+
| Your work stays only in this open page. It is not saved. Closing,       |
| reloading, or leaving loses it. Include only what you need. [Limits]    |
+-------------------+----------------------------------------------------+
| Dashboard         |                                                    |
| Notes             | Selected section                                   |
| Claims            |                                                    |
| Timeline          |                                                    |
| Evidence          |                                                    |
| Risks & gaps      |                                                    |
| Narrative         |                                                    |
| Share / next      |                                                    |
+-------------------+----------------------------------------------------+
```

The limits notice remains visible but uses the same visual weight as ordinary guidance rather
than an alarm treatment. “Limits” opens plain-language details about device visibility, loss on
navigation, access metadata, manual copies, and the share boundary. Final copy and placement need
`[CONTENT] [SECURITY] [A11Y]` review.

On narrow screens, the section list becomes a “Sections” menu before the main heading. The active
section is exposed in text and programmatic state, not color alone. Moving between sections never
submits or serializes draft data. `[SECURITY] [A11Y]`

### Provisional information labels

Issue #2316 asks the prototype to separate core facts from background, emotion, and distracting
details. The least judgmental working labels for testing are:

- **Possible core fact:** a detail the user currently considers central. It must not imply
  verified truth, credibility, or legal materiality.
- **Background / context:** context that may help an audience understand another item. It must
  not pressure exhaustive disclosure.
- **Impact / reaction:** what the user experienced, felt, noticed, or inferred. It must not
  diagnose, minimize emotion, or make emotion a credibility signal.
- **Set aside for now:** an item the user does not want in the current working view. This replaces
  the judgmental “distracting” label and must remain recoverable in page memory.
- **Not categorized:** the default. The user need not sort an item, and the item remains fully
  usable without categorization.

These are optional user-applied labels, not separate mandatory forms. No label is preselected,
and an item can remain uncategorized. Whether the labels should overlap, attach to every section,
or exist at all is `[RESEARCH]`. Their names and explanations require `[CONTENT] [LEGAL]` review.

## Low-Fidelity Section Wireframes

Each wireframe shows the initial empty state. Counts are descriptive within the live page only;
they must not be logged, persisted, treated as progress, or used to rank sections.

### Dashboard

```text
+---------------------------------------------------------------------+
| Dashboard                                            [Discard & leave]|
| Work in any order. You can skip any section or stop at any time.      |
|                                                                     |
| [Notes]             [Claims]              [Timeline]                 |
| Capture pieces      Examine statements    Place events in an order   |
| [Open]              [Open]                [Open]                     |
|                                                                     |
| [Evidence]          [Risks & gaps]         [Narrative]                |
| Map what you have   Review uncertainty    Assemble selected pieces   |
| [Open]              [Open]                [Open]                     |
|                                                                     |
| [Share plan / next action]                                          |
| Continue, pause, explore separately, share selected items, or stop   |
| [Review choices]                                                    |
|                                                                     |
| EMPTY: Nothing has been added. Start anywhere, or leave without      |
|        creating a draft.                                            |
+---------------------------------------------------------------------+
```

The card descriptions are orientation copy only. They do not define the source workflow and need
`[RESEARCH] [CONTENT]` review.

### Notes

```text
+---------------------------------------------------------------------+
| Notes                                                [Discard & leave]|
| Put down a small piece in your own words. Skip anything you do not    |
| want to include.                                      [Why this?]     |
|                                                                     |
| [ Add a note ]                                                      |
|                                                                     |
| EMPTY: No notes yet. You can add one, open another section, or stop. |
|                                                                     |
| When an item exists:                                                |
| +-----------------------------------------------------------------+ |
| | User-entered text                                                | |
| | [Edit] [Move] [Optional label] [Set aside] [Remove]              | |
| +-----------------------------------------------------------------+ |
+---------------------------------------------------------------------+
```

“Why this?” explains the user-selected purpose without suggesting what to disclose. Note size,
splitting, merging, movement, and recovery behavior are `[RESEARCH]`. Editing controls must have a
keyboard and non-spatial equivalent. `[A11Y]`

### Claims

```text
+---------------------------------------------------------------------+
| Claims                                               [Discard & leave]|
| Review statements you may want to examine. The builder does not      |
| decide whether a statement is true or a legal claim. [About claims]  |
|                                                                     |
| [ Add a statement ]                                                  |
|                                                                     |
| EMPTY: No statements here. A claim is not required to use the        |
|        builder or choose a next action.                              |
|                                                                     |
| Item: [User-entered statement]                                      |
|       [Link an existing item] [Optional label] [Edit] [Remove]       |
+---------------------------------------------------------------------+
```

The section title comes from issue #2316, but “claim” can imply a legal cause of action or a
credibility judgment. The title, explanatory copy, and whether this section should exist require
`[RESEARCH] [LEGAL] [CONTENT]` review. Links express only a relationship chosen by the user; the
builder does not infer support or contradiction.

### Timeline

```text
+---------------------------------------------------------------------+
| Timeline                                             [Discard & leave]|
| Arrange events only if order helps you. Exact dates and locations can |
| identify people; include only what you need.                          |
|                                                                     |
| [ Add an event ]                                                     |
|                                                                     |
| EMPTY: No events yet. You can use another section without making a   |
|        timeline.                                                     |
|                                                                     |
| [Earlier / later / unsure]  User-entered event                       |
| [Reorder] [Date precision: user choice] [Edit] [Set aside] [Remove]  |
+---------------------------------------------------------------------+
```

Dates are optional and allow imprecise user-entered descriptions; the prototype does not require
a calendar value. Relative ordering, uncertainty labels, and whether chronology is useful need
`[RESEARCH]`. Identification guidance and date handling need `[SECURITY] [CONTENT]` review.

### Evidence

```text
+---------------------------------------------------------------------+
| Evidence                                             [Discard & leave]|
| Map information you already have. Do not gather anything new because |
| of this builder. The builder does not verify or score evidence.       |
|                                                                     |
| [ Add a reference ]                                                  |
|                                                                     |
| EMPTY: No references yet. Evidence is not required, and this section |
|        is not a checklist.                                           |
|                                                                     |
| Item: [User-entered description; no file upload]                     |
| Relates to: [Choose an existing item]                                |
| Relationship: [Supports / conflicts / leaves uncertainty / unmarked]|
| [Edit] [Remove]                                                      |
+---------------------------------------------------------------------+
```

This section accepts descriptions only in the proposed MVP; it has no attachment, metadata,
preview, import, or evidence-gathering flow. Relationship terms are user assertions, not product
analysis, and require `[RESEARCH] [LEGAL] [CONTENT]` review. The prohibition on asking a
whistleblower to proactively gather further evidence follows ISO 37002 section 8.2.3.

### Risks and gaps

```text
+---------------------------------------------------------------------+
| Risks & gaps                                          [Discard & leave]|
| Optionally review uncertainty and details that may identify or affect |
| you or someone else. This does not predict risk or recommend action.   |
|                                                                      |
| [ Mark something to review ]                                         |
|                                                                      |
| EMPTY: Nothing marked for review. You do not need to find or fill     |
|        gaps.                                                          |
|                                                                      |
| Review item: [User-entered concern or linked existing item]           |
| [Uncertain] [May identify someone] [May be unnecessary] [Custom]      |
| [Keep] [Revise] [Set aside] [Remove]                                 |
+---------------------------------------------------------------------+
```

The section never calculates severity, credibility, completeness, urgency, or retaliation risk.
It does not tell a user to fill a gap. The name, review labels, personal-safety boundaries, and
responses to imminent-harm language require `[RESEARCH] [SECURITY] [LEGAL] [CONTENT]` review.

### Narrative

```text
+---------------------------------------------------------------------+
| Narrative                                             [Discard & leave]|
| Assemble only the pieces useful for the audience you have in mind.    |
| The builder does not generate, score, or call a draft complete.        |
|                                                                      |
| Available items                    Current narrative                  |
| +-----------------------------+    +-------------------------------+ |
| | [Add this item] Item A      | -> | Selected item B               | |
| | [Add this item] Item B      |    | [Reorder] [Edit copy] [Remove]| |
| +-----------------------------+    +-------------------------------+ |
|                                                                      |
| EMPTY: Select an existing item or write a new piece. A narrative is   |
|        optional.                                                      |
+---------------------------------------------------------------------+
```

Nothing is selected automatically. Edits in the narrative are a working copy and do not silently
rewrite source items. Preset audiences, templates, drafting assistance, and claims of completeness
are outside this prototype. Selection and ordering need a non-drag alternative. `[A11Y]`

### Share plan / next action

```text
+---------------------------------------------------------------------+
| Share plan / next action                              [Discard & leave]|
| Choose what, if anything, feels useful now. None is recommended.       |
|                                                                      |
| ( ) Continue in any section                                           |
| ( ) Pause while keeping this page open                                |
| ( ) Explore a Hush Line recipient separately                          |
| ( ) Share selected items in an available Hush Line account chat       |
| ( ) Discard the visible draft and leave                               |
|                                                                      |
| [Continue with selected choice] [Return to workspace]                 |
|                                                                      |
| EMPTY: No choice selected. Nothing happens until you choose.          |
+---------------------------------------------------------------------+
```

“Pause” is not persistence: the page must stay open, and a reload, navigation, crash, or power
loss loses the draft. Recipient exploration opens a separate existing discovery surface without
draft content, a case identifier, or a recommended recipient. `[SECURITY] [CONTENT]`

The account-chat choice remains blocked on protocol design review. If later approved, it expands
into two explicit review states:

```text
Share review 1 of 2: Choose content
+---------------------------------------------------------------------+
| [ ] Item A     [ ] Item B     [ ] Item C                              |
| No items are preselected.                                             |
|                                         [Cancel] [Review selected]     |
+---------------------------------------------------------------------+

Share review 2 of 2: Confirm exact copy and participant
+---------------------------------------------------------------------+
| To: [confirmed account-chat participant / conversation]               |
| Exact plaintext that will be encrypted and sent:                      |
| +------------------------------------------------------------------+ |
| | selected content only                                             | |
| +------------------------------------------------------------------+ |
| This leaves the local draft. The recipient can read and copy it.     |
| Hush Line stores encrypted copies and account/conversation metadata. |
| Discarding this draft will not delete a sent message.                |
|                                                                      |
| [Cancel and return]                         [Confirm encrypted share] |
+---------------------------------------------------------------------+
```

Authentication, locked keys, changed participant keys, authorization errors, encryption errors,
and network errors must stop without transmitting or persisting plaintext. The exact participant,
metadata, retention, and copy text requires `[SECURITY] [CONTENT] [LEGAL] [A11Y]` review.

## Choosing Not to Proceed

“Discard & leave” is present in the global shell and the next-action screen. It does not require a
reason and does not frame stopping as failure.

```text
+---------------------------------------------------------------------+
| Discard the visible draft?                                           |
| This clears the builder's visible work from this page and leaves.    |
| It is not a promise of secure erasure from device memory or captures.|
|                                                                     |
| [Keep working]                              [Discard draft and leave] |
+---------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------+
| Neutral destination outside the builder                             |
| You chose not to continue. Nothing was sent or saved by the builder. |
| [Go to Hush Line home]                       [Start again, empty]      |
+---------------------------------------------------------------------+
```

Before navigation, implementation must replace sensitive rendered content and clear application
references. It must not record the choice, store the draft, or claim forensic erasure. The final
destination and whether a confirmation creates unacceptable delay require `[RESEARCH] [SECURITY]
[CONTENT]` review.

## Navigation and State Rules

- **First visit:** show limits before entry; create no case record or identifier.
- **Open a section:** navigate directly, with no prerequisite section or completion gate.
- **Empty section:** explain that it is optional; offer add, navigate elsewhere, or stop.
- **Return to dashboard:** show neutral in-page item counts only; do not show a percentage or
  recommended next section.
- **Set an item aside:** hide it from the working view; allow restore while the page remains open.
- **Remove an item:** remove it from the in-memory draft after a reversible in-page confirmation.
- **Reload, close, or navigate away:** restore nothing; warn accurately before loss where browser
  behavior permits.
- **Back/forward or tab restoration:** restore no draft.
- **Open recipient discovery:** transfer no content or state; explain that leaving loses the
  draft.
- **Cancel share:** return to the builder and transmit nothing.
- **Share failure:** keep the local page state if possible; transmit no plaintext or fallback
  payload.
- **Discard and leave:** clear rendered content and references, then navigate; collect no reason
  or metric.

All add, edit, remove, set-aside, restore, link, reorder, selection, and navigation actions need
keyboard operation, visible focus, meaningful accessible names, and status announcements that do
not expose content beyond the page. Visual relationships must also be available as an ordered
text list. `[A11Y] [SECURITY]`

## Required Human Review

- **IA-R-01 — Source stakeholder and product:** validate or revise the section names, categories,
  nonlinear movement, item granularity, breakdowns, recovery behavior, and useful output before
  interactive design or implementation.
- **IA-R-02 — Content and accessibility:** confirm that all headings, descriptions, empty states,
  “why this?” help, warnings, and discard language are neutral, comprehensible, and
  non-interrogative.
- **IA-R-03 — Qualified legal reviewer and content:** review “claims,” “evidence,” “core fact,”
  “risks,” “gaps,” narrative, and every non-advice boundary to prevent legal classification,
  sufficiency, privilege, or outcome cues.
- **IA-R-04 — Security/privacy and maintainers:** accept or revise the threat-model boundary for
  memory-only operation, navigation loss, cache/storage behavior, device notice, and discard
  semantics.
- **IA-R-05 — Security/privacy and chat maintainers:** approve a fail-closed design for item
  selection, participant confirmation, authentication and key failures, E2EE handoff, and
  metadata against the implemented chat protocol.
- **IA-R-06 — Accessibility and representative users:** prove an equivalent non-spatial,
  keyboard, and screen-reader experience for landmark order, responsive navigation, focus,
  announcements, reordering, links, and warnings.
- **IA-R-07 — Product, security, content, and legal:** ensure the explore-recipient transition and
  final destination after discard cause no draft transfer, recommendation, false protection, or
  shame.
- **IA-R-08 — Security/privacy and content:** define safe, non-monitoring behavior for imminent
  harm or retaliation without claiming to provide emergency help.

No reviewer, jurisdiction, or stakeholder approval is currently recorded. These are release and
implementation blockers, not permission to select wording or behavior by assumption.

## Acceptance-Criteria Traceability

- **Wireframes for every MVP section:** Dashboard, Notes, Claims, Timeline, Evidence, Risks &
  gaps, Narrative, and Share plan / next action.
- **Navigation covered:** flat IA map, global shell, responsive navigation note, and state rules.
- **Empty states covered:** an explicit empty state appears in every section wireframe.
- **Path for choosing not to proceed:** persistent discard action, next-action choice,
  confirmation, and cleared state.
- **Legal/security review content identified:** inline annotations and review register IA-R-03
  through IA-R-08.
- **Preparation without interrogation:** optional sections, neutral empty states, and no required
  sequence or completion score.
- **Nonlinear use:** flat navigation and no prerequisites between sections.
- **Safety reminders visible but not alarming:** persistent compact limits notice plus contextual
  guidance.
- **Core facts separated from other material:** optional provisional labels, including a neutral
  “set aside for now” path.

## Prototype Exit Gate

This IA may advance to interactive design only after the source-workflow memo's evidence and
playback gate is complete and IA-R-01 through IA-R-08 have named reviewers and recorded decisions.
If review changes the categories, navigation, useful output, persistence boundary, or sharing
model, update this document, the threat model, the MVP user stories, and `docs/USE-CASES.md` before
implementation. Until then, this document remains a structural prototype and must not be treated
as validated product behavior.
