# Secure Case Builder Source Workflow Research Memo

Last updated: 2026-09-18

Linked issue: #2319

Parent epic: #2315

## Research Status

The source-stakeholder interview has not been supplied or conducted. The repository and issue
contain no first-hand account of the sticky-note exercise. Therefore, the source categories,
sorting order, breakdowns, decision points, and source-specific negative boundaries remain
`Unknown`.

This memo is the research record and interview/synthesis structure for that missing evidence. It
must not be treated as a validated source-workflow specification. Wireframes and implementation
stories that depend on the source workflow are blocked until the evidence and validation gates
below are complete.

| Evidence needed                          | Available | Consequence                                                         |
| ---------------------------------------- | --------- | ------------------------------------------------------------------- |
| First-hand walkthrough of the exercise   | No        | The workflow cannot be reconstructed                                |
| Exact or stakeholder-approved categories | No        | Product information architecture cannot be selected                 |
| Observed or recalled ordering behavior   | No        | A fixed sequence would be an unsupported design decision            |
| Breakdowns and recovery strategies       | No        | Guidance and error-recovery behavior cannot be designed responsibly |
| Stakeholder-validated workflow synthesis | No        | The research phase cannot be accepted as complete                   |

## Evidence Boundary

The issue establishes only the following facts:

- A sticky-note workflow inspired the Secure Case Builder concept.
- The intended research concerns categories, sorting order, breakdowns, useful decisions, and
  harmful prompts or implications.
- Sensitive details must be fictionalized or omitted.

Everything else in this memo is either an interview prompt, a synthesis field, an existing Hush
Line/ISO 37002 safety constraint, or a candidate opportunity requiring validation. None of it is
an interview finding.

Use these evidence labels in future updates:

- `Observed`: directly seen during a stakeholder demonstration.
- `Reported`: stated by the stakeholder but not directly observed.
- `Inferred`: interpretation by the researcher; requires stakeholder validation.
- `Existing constraint`: grounded in Hush Line policy, use cases, or ISO 37002 rather than the
  source interview.
- `Open`: unanswered.

## Privacy-Preserving Interview Protocol

### Data handling

- Ask the stakeholder to demonstrate with invented or already-sanitized material, not a real
  person's case.
- Do not request names, employers, locations, dates, contact details, account identifiers, medical
  information, legal strategy, or source documents.
- Stop and redirect if an answer begins to identify a whistleblower, subject, witness, or other
  person. Record the workflow pattern only.
- Do not record audio or video by default. If recording is separately approved and consented to,
  define access and deletion before the interview begins.
- Store only sanitized notes in this repository. Keep raw research material and participant
  identity out of commits, issue comments, screenshots, analytics, and test fixtures.
- Let the stakeholder decline any question and review the synthesized workflow before it is used
  for product decisions.

### Opening frame

Explain that the goal is to understand the mechanics of the exercise, not the underlying case or
the participant's personal history. Ask the stakeholder to use fictional examples and to correct
the interviewer whenever a label, sequence, or interpretation is wrong.

### Walkthrough prompts

Ask for a demonstration before asking the stakeholder to generalize.

1. What prompted someone to begin the sticky-note exercise?
2. What did a blank note represent, and how did someone decide what belonged on one note?
3. What labels or categories were available? Capture the stakeholder's language exactly, then ask
   what each label meant and whether labels could overlap.
4. Were the categories present at the start, discovered while sorting, or both?
5. Starting from an unsorted set, what did the person do first, next, and last? Ask what could
   happen in parallel, be skipped, or be repeated.
6. What caused a note to move, split, merge, be duplicated, or be discarded?
7. What decisions changed the exercise from recounting events or feelings into a usable plan?
8. How did someone know they had enough information for the next step?
9. Where did people pause, loop, add too much, become uncertain, or abandon the exercise?
10. What did a facilitator do at those moments? Which interventions helped, and which made things
    worse?
11. Which information was intentionally excluded, deferred, generalized, or kept off the notes?
12. What was the output: a decision, a sequence of actions, questions for an adviser, a report, or
    something else? Who was it for?
13. What did the exercise never ask? What must a digital version never promise, judge, or imply?
14. What parts depended on physical space, moving notes by hand, another person's presence, or the
    ability to step away?
15. If the stakeholder could preserve only one property of the exercise, what would it be?

For every step, ask for a fictional example, the reason for the step, its input and output, the
choice it enabled, and what happened when it failed.

### Playback and validation

At the end of the session, play back:

- the category names and definitions;
- the usual path plus every loop, optional step, and exit;
- the points where users became stuck, spiraled, over-disclosed, or lost confidence;
- the decisions that moved a person toward a plan; and
- the explicit list of things the product must not ask, promise, judge, or imply.

Ask the stakeholder to mark each item as accurate, inaccurate, or incomplete. A later repository
update should preserve the sanitized corrections, not the identifying interview context.

## Interview Notes

No stakeholder notes are available yet. Add only sanitized, stakeholder-reviewable observations
to this table.

| Evidence label | Activity or decision | Stakeholder language | Input | Output | Breakdown or recovery | Safety boundary |
| -------------- | -------------------- | -------------------- | ----- | ------ | --------------------- | --------------- |
| Open           |                      |                      |       |        |                       |                 |

## Current-State Workflow Map

The source workflow cannot yet be mapped. Populate this structure from the demonstrated exercise;
do not replace the placeholders with product-team assumptions.

```text
[Trigger: Unknown]
        |
        v
[First action: Unknown] ---> [Early exit or pause: Unknown]
        |
        v
[Sorting/grouping steps and order: Unknown]
        |
        +----------> [Loop/recovery: Unknown]
        |
        v
[Decision that creates a usable plan: Unknown]
        |
        v
[Output, audience, and handoff: Unknown]
```

For each node and transition, record whether it is `Observed`, `Reported`, or `Inferred`; what the
person is trying to accomplish; what information is visible; what decision is made; and what
privacy or confidence risk exists. Show optional paths and loops rather than forcing the account
into a linear sequence.

## Candidate Opportunity Register

These are research questions, not product recommendations. Promote one to an opportunity only
when interview evidence identifies the problem and stakeholder playback validates the
interpretation.

| Area           | Candidate opportunity to evaluate                                       | Evidence required                                                     | Existing constraint                                                                  |
| -------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Product        | Make small pieces of information easy to externalize and rearrange      | Note granularity and the value of physical movement                   | A suggested structure must not become prescriptive                                   |
| Product        | Preserve pause, resume, skip, undo, and non-linear movement             | Where people pause, loop, or safely leave the exercise                | Do not trap a distressed person in a completion flow                                 |
| Product        | Make the transition from reflection to a next step explicit             | The decisions that actually produced a useful game plan               | Do not imply that completing the builder makes a report complete, true, or safe      |
| Product        | Support a useful output without requiring every detail                  | Minimum sufficient output and its intended audience                   | Collect only what is necessary for the user's chosen purpose                         |
| Security       | Warn about identifying or unnecessarily sensitive detail in context     | Moments and content types associated with over-disclosure             | Do not inspect, transmit, or retain plaintext merely to provide guidance             |
| Security       | Minimize exposure of drafts, labels, and abandoned work                 | Expected device use, handoff, persistence, and recovery needs         | E2EE, anonymity, confidentiality, and plausible-deniability guarantees remain intact |
| Content design | Use neutral prompts that restore confidence without judging credibility | Language used at uncertainty and recovery points                      | Avoid coercive, diagnostic, legal, or credibility-scoring language                   |
| Content design | Explain why a prompt is asked and allow it to be skipped                | Which prompts need context and which information is optional          | Do not make optional identity or case details appear required                        |
| Content design | Separate facts, interpretations, feelings, risks, and desired outcomes  | Only if the stakeholder's actual categories or decisions support this | Do not import these candidate categories into wireframes as a finding                |

## Established Non-Goals and Harmful Patterns

The following are existing safety boundaries, not claimed stakeholder findings:

- Do not assess whether a person is a whistleblower, whether an allegation is true, or whether a
  case is strong enough.
- Do not provide legal, medical, mental-health, investigative, employment, or emergency-response
  advice, or imply that the tool replaces a qualified human.
- Do not promise safety, anonymity, confidentiality, a particular outcome, or protection from
  retaliation merely because the workflow was completed.
- Do not ask a person to proactively gather more evidence. ISO 37002 explicitly says a
  whistleblower should not be asked to do this.
- Do not require names or other identifying details when the user's chosen outcome does not need
  them, and do not imply that disclosure is more credible when identity is provided.
- Do not turn categories into diagnoses, legal conclusions, credibility scores, mandatory gates,
  or a universal sequence.
- Do not reward exhaustive disclosure, urgency, or completion in ways that encourage a person to
  reveal more than is needed.
- Do not shame, challenge, cross-examine, or use language that blames a person for uncertainty,
  missing information, delay, or a decision not to report.
- Do not expose draft contents, category labels, or interaction history to logs, analytics,
  notifications, or third parties.
- Do not design an exit, save, export, collaboration, or handoff flow until its device traces,
  metadata, retention, access, and deletion risks have been reviewed.
- Do not implement the source workflow from this placeholder memo. The stakeholder's own
  source-specific non-goals and harmful patterns are still `Open`.

## Open Product Questions

| ID     | Question                                                                      | Evidence or decision owner needed                          | Status  |
| ------ | ----------------------------------------------------------------------------- | ---------------------------------------------------------- | ------- |
| SCB-01 | What were the stakeholder's exact categories and definitions?                 | Source-stakeholder demonstration and playback              | Blocked |
| SCB-02 | Were categories predefined, emergent, overlapping, or optional?               | Source-stakeholder demonstration                           | Blocked |
| SCB-03 | What was the actual order, including loops, skips, and stopping points?       | Source-stakeholder demonstration and playback              | Blocked |
| SCB-04 | Which breakdowns were observed versus inferred by a facilitator?              | Source stakeholder; sanitized observational evidence       | Blocked |
| SCB-05 | Which interventions restored agency, clarity, or confidence?                  | Source stakeholder; sanitized examples                     | Blocked |
| SCB-06 | What decision or artifact counted as a usable game plan, and for whom?        | Source stakeholder                                         | Blocked |
| SCB-07 | What must the product never ask, promise, judge, or imply?                    | Source stakeholder, followed by content/security review    | Blocked |
| SCB-08 | Should drafts persist, and on which device or trust boundary?                 | User evidence, threat modeling, and security decision      | Blocked |
| SCB-09 | How can users recognize and remove identifying or excessive detail safely?    | User evidence, content design, and E2EE architecture       | Blocked |
| SCB-10 | What outputs and handoffs are useful without expanding collection or risk?    | Source stakeholder, product, security, and recipient users | Blocked |
| SCB-11 | What accessibility needs change sorting, spatial layout, or interaction mode? | User research and accessibility review                     | Blocked |
| SCB-12 | What crisis, retaliation, or imminent-harm boundaries require safe exits?     | Security, content, and qualified human review              | Blocked |

## Completion Gate

This research issue is ready to inform wireframes and user stories only when all of the following
are true:

- Sanitized interview notes answer SCB-01 through SCB-07 with evidence labels.
- The workflow map shows categories, sequence, loops, exits, breakdowns, recovery, decisions, and
  output without including sensitive case details.
- The source stakeholder has corrected or approved the synthesized map and negative boundaries.
- Opportunities are traceable to evidence and separated from product-team hypotheses.
- Product, security, accessibility, and content reviewers have recorded unresolved decisions in
  the open-question table instead of silently resolving them in wireframes.
- `docs/USE-CASES.md` is updated if the validated research adds or materially changes a workflow.
