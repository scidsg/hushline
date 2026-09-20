# Secure Case Builder Case-Education Library Recommendation

Last updated: 2026-09-19

Linked issue: #2325

Parent epic: #2315

Prerequisite: #2317

## Decision

**Defer the similar-case / law-library component from the Secure Case Builder MVP.** Do not add a
library, case matching, legal search, or case-specific education to the builder. The phrase
"similar case" itself implies a comparison that the product is not qualified to make.

A future **case-education library may be prototyped separately** only after the release gates in
this document are complete. That prototype should be a public, static, curated collection of
general educational summaries. It must not receive builder content, ask for facts, identify a
user's legal issue, rank cases by similarity, or recommend a course of action.

This decision keeps the accepted [MVP user stories](./SECURE-CASE-BUILDER-MVP-USER-STORIES.md)
within their educational, non-predictive boundary. It also avoids creating an account or activity
link for reading public information and preserves the
[pre-build threat model](./SECURE-CASE-BUILDER-THREAT-MODEL.md), which treats case structure and
interaction history as sensitive.

The library is not ready to prototype now. No jurisdictional scope, qualified legal reviewer,
content owner, update process, or validated user need has been supplied. Those are blockers, not
details for an implementation team to infer.

## Educational Scope

The future library's purpose would be to help a reader understand how a published authority
described and handled a matter. An entry may explain:

- the jurisdiction, decision-maker, date, and procedural stage;
- the material facts **as the authority reported them**, including disputed or unresolved facts;
- the legal or administrative question the authority addressed;
- the rule, standard, or burden the authority said it applied;
- the kinds of information the authority discussed, without turning them into an evidence
  checklist;
- the result at that procedural stage, including dissents or material limitations; and
- known later history and the date on which a human last checked the entry.

Entries must be descriptive and attributed. Prefer wording such as "the court stated," "the
agency considered," and "at this procedural stage." A summary must distinguish allegations,
findings, party arguments, and the editor's plain-language explanation.

The library must not:

- decide that a reader is a whistleblower or that a library entry is similar to their situation;
- accept, inspect, import, or derive facts from a builder draft, message, account, or search query;
- assess credibility, sufficiency, eligibility, claim strength, evidentiary value, or likely
  outcome;
- tell a reader what evidence to obtain, preserve, reveal, or withhold;
- recommend a deadline, forum, recipient, legal theory, negotiation position, or reporting
  strategy;
- generate legal arguments, filings, correspondence, or personalized questions;
- imply that a result, remedy, protection, privilege, or confidentiality rule will apply to the
  reader; or
- present a summary as a substitute for the complete source or advice from a qualified lawyer in
  the relevant jurisdiction.

These limits are functional, not merely a disclaimer. If an interaction needs a reader's facts to
select, adapt, rank, or explain content, it is outside this education-library proposal.

## Source Policy

### Sources that may support an entry

Each legal proposition and case-specific statement must be traceable to a named, reviewable
source. Use this priority order:

1. **Official primary authority:** constitutions, enacted legislation, regulations, court
   opinions and orders, official dockets, and adjudicative agency decisions from the body or its
   designated official publisher.
2. **Official explanatory material:** current guidance, manuals, and public education published
   by a court, legislature, regulator, or other government body. Label guidance as guidance and
   do not present it as binding authority.
3. **Reviewed public legal education:** material maintained by a recognized legal-aid,
   professional, academic, or standards body may explain context that the primary source does not
   make accessible. A qualified legal reviewer must approve its use, and the entry must still
   link to primary authority for legal propositions where primary authority is publicly
   available.

The publisher must be identifiable, the source must be publicly inspectable, and its jurisdiction,
date, version, and status must be recorded. If the canonical source is inaccessible, incomplete,
or cannot be authenticated, do not publish the entry until a legal reviewer approves a reliable
substitute and the substitution is disclosed.

### Sources that may locate, but not substantiate, an entry

News coverage, law-firm articles, commercial research headnotes, search snippets, crowd-edited
pages, advocacy material, and machine-generated text may identify a candidate source. They must
not be the sole support for an entry or be silently paraphrased as authority. Editorial summaries
and headnotes are not the underlying decision.

### Sources and content that are excluded

Do not publish from leaked, sealed, expunged, unlawfully obtained, or non-public material; private
client files; user submissions; or builder/message content. Do not reproduce personal or
identifying details merely because they appear in a public record. Include only details necessary
to understand the educational point, and have the content and legal reviewers assess risks to
whistleblowers, witnesses, subjects, minors, and other vulnerable people.

Machine output is never a source. A citation must resolve to the material a reviewer actually
read, and every quotation must be checked against that source and kept to the minimum needed.

## Discussing Evidence Without Predicting Outcomes

An entry may accurately report a named authority's standard and what was in that authority's
record. It must keep four distinctions visible:

- **jurisdiction:** rules and terminology can differ across places and decision-makers;
- **time:** law, guidance, and later treatment can change;
- **procedural posture:** a threshold at intake, pleading, interim relief, trial, appeal, or an
  administrative process answers a different question; and
- **record:** a published result concerns the record and arguments before that decision-maker,
  not an unnamed reader's circumstances.

Do not translate those descriptions into a universal quantity or checklist. Avoid labels such as
"enough evidence," "winning case," "strong claim," and "likely outcome." Do not calculate a
score, probability, gap analysis, or comparison. The product may say that a decision-maker
discussed particular material; it must not say that a reader needs the same material or should go
obtain it. This also preserves ISO 37002's boundary that a whistleblower should not be asked to
proactively gather further evidence.

## Access and Privacy Boundary

If the release gates are eventually met, publish the same educational collection to visitors
whether or not they have an account. Reading must not require login, and signing in must not add
saved cases, favorites, recommendations, history, or personalization.

The prototype should use fixed first-party pages and assets. It must have no free-text case intake,
third-party embeds, third-party analytics, or library-specific telemetry. If browsing needs
filters, they must use predefined public catalog fields and operate client-side without
transmitting selections or creating identifiers. Do not provide a free-text "describe your case"
or similarity search. Ordinary route-access logs remain possible and must follow the existing
retention and access policy; copy must not promise unobservable or anonymous access.

The library must be separate from the builder route and state. It must not receive draft text,
labels, relationships, recipient choices, or account context. Navigating to education must not
save, transfer, or transform a draft, and the interface must accurately warn that leaving or
reloading the memory-only builder loses the draft.

## Required Boundaries and Notices

The boundaries must appear in the product structure, labels, and entry format. A page-level notice
alone cannot make personalized analysis educational.

Before browsing and alongside each entry, reviewed plain-language copy must communicate, at
minimum:

> This library provides general educational summaries of published materials. It is not legal
> advice and does not assess your situation, tell you what evidence to collect, or predict an
> outcome. Law and source status can change. Read the linked source and consider seeking advice
> from a qualified lawyer in the relevant jurisdiction.

Each entry must also display its jurisdiction, source type, procedural stage, source date, last
human-review date, and a link to the source. Where applicable, it must state that guidance is
non-binding, a decision has later history, facts were disputed, or the result was limited to a
particular stage.

The notice must not claim that browsing creates confidentiality, anonymity, legal privilege, an
attorney-client relationship, representation, protection from retaliation, deadline protection,
or a complete statement of current law. Final wording and placement require qualified legal,
content, accessibility, and security review in context.

## Content Record and Review Process

Every proposed entry needs a review record containing:

- stable identifier and citation;
- canonical source link and an archived or versioned reference when lawful and available;
- source class, jurisdiction, issuing body, date, and procedural posture;
- scoped educational purpose and intended audience;
- proposition-to-source notes for every legal statement;
- later-history and current-status check;
- personal-data minimization decision;
- author, reviewers, approvals, version, and last-checked date; and
- correction, withdrawal, and next-review status.

Release requires all of these human approvals:

1. A content researcher prepares the source record and draft without adding unsupported
   conclusions.
2. A lawyer qualified for the covered jurisdiction verifies the source, legal accuracy,
   treatment, scope, terminology, and non-advice boundary.
3. A content/UX reviewer checks plain language, attribution, neutral framing, and that the entry
   does not pressure disclosure or evidence gathering.
4. A security/privacy reviewer verifies data flow, logging, source-integrity, personal-data, and
   separation-from-builder controls.
5. An accessibility reviewer verifies the notice, citations, status, and distinctions remain
   understandable and operable without relying on color or visual layout.
6. A designated maintainer confirms that all approvals are recorded before publication.

The qualified lawyer and designated maintainer must be identified before a prototype begins.
Counsel must set a review interval appropriate to each source type and jurisdiction. Amendment,
reversal, superseding authority, broken provenance, a reported error, or uncertainty about current
status triggers immediate review; hide the affected entry until the uncertainty is resolved. A
visible correction and withdrawal path is required.

## Automation Gate

No automated or AI-assisted collection, summarization, translation, classification, similarity
matching, recommendation, citation checking, later-history checking, or publication may be built
or enabled until legal, security/privacy, content, and accessibility reviewers approve a written
proposal for that exact use.

The proposal must define provenance, source allowlists, untrusted-source handling, data flows,
retention, evaluation for fabrication and misleading omission, jurisdiction and currency checks,
human approval before every publication or update, correction and rollback, and monitoring that
does not collect reader or builder activity. Automation must never receive a builder draft,
message, account context, or other case-specific user data. A disclaimer or human spot check does
not waive these gates.

## Prototype Readiness Gate

A separate prototype remains blocked until:

- stakeholder research validates a need for general case education rather than personalized case
  comparison;
- product owners choose and document a bounded jurisdiction, audience, topic, and entry set;
- a qualified lawyer for that jurisdiction accepts the scope, source policy, entry template,
  notice, review interval, and correction process;
- content, security/privacy, and accessibility reviewers approve the static public design and its
  separation from the builder;
- named owners accept publication, update, withdrawal, and incident-response duties; and
- representative entries complete the full review process without using automation.

Until every item is recorded, the MVP and prototypes must contain no case-education library or
similar-case functionality.
