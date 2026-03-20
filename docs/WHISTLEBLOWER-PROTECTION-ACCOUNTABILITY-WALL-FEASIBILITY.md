# Real-Time Whistleblower-Protection Accountability Wall Feasibility Memo

Last updated: 2026-03-20

This memo evaluates whether Hush Line should add a public feature that tracks politicians who attack whistleblowers or weaken whistleblower protections, scores them based on evidence, and later helps constituents contact them.

This is a feasibility and policy memo only. It is not approval to build or launch the feature.

## Recommendation

Recommendation: `Decline` for the Hush Line product.

Why:

- The feature is a poor fit for Hush Line's core mission as safety-critical whistleblower infrastructure.
- A public politician scorecard would materially increase legal, governance, moderation, and reputational risk.
- "Real-time" publication is incompatible with the level of human review required to avoid false attribution, defamation risk, and harassment amplification.
- In-product constituent-contact tooling would create a new advocacy/lobbying surface, new personal-data collection, and a new abuse channel that is not necessary for the whistleblower flow.

If maintainers still want related work later, the narrowest viable follow-up is not a Hush Line feature. It is a separate, explicitly editorial research project that publishes evidence-backed reporting without real-time claims, without in-product outreach, and without automated scoring.

## Executive Summary

The proposed feature has some technically feasible inputs, but the overall product shape is not a strong match for Hush Line.

What is feasible:

- Collecting federal bill metadata and many recorded votes from official congressional sources.
- Collecting official written statements from government websites and press-release pages.
- Building an internal evidence ledger with reproducible provenance and human review.

What is not currently feasible at acceptable risk:

- A trustworthy real-time public score that updates automatically from mixed public-web inputs.
- High-confidence attribution of social-media statements at scale across platforms with stable API access and low operations burden.
- In-product constituent outreach that remains clearly within Hush Line's mission and does not create a new regulated advocacy workflow.

The key constraint is not raw engineering difficulty. It is the governance layer needed to make the output accurate, explainable, appealable, and non-abusive.

## Mission and Governance Fit

Hush Line's primary duty is to protect anonymous disclosures. A public accountability wall aimed at elected officials changes the product's role from secure infrastructure into political publishing and advocacy support.

That shift creates several problems:

- It weakens mission clarity. Hush Line would no longer be understood only as a secure intake and inbox system.
- It increases adversarial attention from political actors, their staff, and coordinated supporters.
- It creates editorial obligations that Hush Line does not currently appear to staff for: evidence review, disputes, corrections, appeals, and publication standards.
- It risks public confusion between whistleblower protection as a civil-liberties mission and support for or opposition to specific candidates or officeholders.

For a U.S. `501(c)(3)`, the governance risk is substantial. The IRS says `501(c)(3)` organizations are absolutely barred from political campaign intervention and may engage in only limited lobbying; urging the public to contact legislators about legislation can count as lobbying, and public statements for or against candidates are prohibited.[^irs-campaign][^irs-lobbying]

Inference from those rules: a politician scorecard tied to public pressure and later contact tooling would need dedicated legal review, election-period controls, and a documented nonpartisan editorial standard before any implementation decision.

## Current Feasibility by Source Category

| Source category                             | Example sources                                                                                                            | Reliability    | Automation fit | Main risks                                                                     | Recommendation                                        |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------- |
| Federal bill metadata                       | [Congress.gov API](https://api.congress.gov/), Congress.gov                                                                | High           | High           | API key required; model gaps still exist                                       | Viable for internal evidence intake                   |
| House recorded votes                        | [Clerk of the House vote pages](https://clerk.house.gov/Votes), XML views                                                  | High           | High           | Covers recorded floor votes, not all legislative behavior                      | Viable for official vote evidence                     |
| Senate roll call votes                      | [Senate vote tables/XML](https://www.senate.gov/general/XML.htm)                                                           | High           | High           | Only roll call votes are individually attributable                             | Viable for official vote evidence                     |
| Congressional Record / floor text           | [Congressional Record](https://www.govinfo.gov/app/collection/crec) and Congress.gov links                                 | High           | Medium         | Text is large and context-sensitive; statement extraction needs review         | Viable as supporting evidence, not auto-scored alone  |
| Official member websites and press releases | `.house.gov`, `.senate.gov`, state-legislature sites                                                                       | Medium to High | Medium         | Site layouts vary; vendor-hosted pages change; statement context can be subtle | Viable with strict allowlists and human review        |
| Committee websites and hearing records      | Committee pages, hearing transcripts, prepared statements                                                                  | Medium to High | Medium         | Delayed publication; difficult parsing; excerpt context risk                   | Viable as secondary evidence                          |
| Official YouTube channels                   | Official office channels, committee channels, [YouTube Data API](https://developers.google.com/youtube/v3/getting-started) | Medium         | Medium         | Quotas; captions/transcripts may be incomplete; clip context can mislead       | Optional supporting evidence only                     |
| X posts                                     | [X API docs](https://developer.x.com/en/docs/twitter-api)                                                                  | Low to Medium  | Low            | Paid access, restrictive limits, policy volatility, repost/deletion drift      | Not viable for an MVP                                 |
| Facebook / Instagram posts                  | Official pages                                                                                                             | Low to Medium  | Low            | Unstable access patterns and high maintenance burden                           | Do not use for MVP scoring                            |
| News reports / NGO reports                  | Reporting or advocacy publications                                                                                         | Medium         | Low            | Defamation amplification, editorial disagreement, bias disputes                | Use only as research leads, never as scoring evidence |
| User-submitted allegations                  | Public uploads or tips                                                                                                     | Low            | Low            | Fabrication, brigading, disclosure risk, massive moderation load               | Non-viable                                            |

## What Official Legislative Data Can and Cannot Prove

Official congressional sources are the strongest foundation because they are attributable, reproducible, and persistent.

Important limits:

- Not every action is a named vote. The Senate states that voice votes and division votes do not identify how each member voted.[^senate-votes]
- Congress.gov is strong for bill metadata, summaries, actions, and member data, but vote ingestion still appears to require combining chamber-specific sources in practice.[^congress-api][^congress-api-vote-gap]
- Member identity resolution is not trivial across time because offices, districts, and terms change.[^congress-member-issue]

Inference from those limits: a defensible system could score only narrowly defined, named, official events. It could not claim to represent every relevant action taken by an elected official.

## Candidate Evidence Types and Provenance Requirements

If this idea were ever revisited, each published evidence item should include all of the following:

- `subject_type`: senator, representative, governor, state legislator, or officeholder category
- `subject_id`: stable canonical identifier
- `event_type`: vote, sponsorship, public statement, press release, hearing statement, policy action
- `jurisdiction`: federal or exact state body
- `source_class`: official vote feed, official government site, official office website, official office video channel
- `source_url`: exact canonical URL
- `retrieved_at`: timestamp of fetch
- `published_at`: timestamp from the source if present
- `verbatim_excerpt`: minimal necessary excerpt only
- `review_notes`: explanation of why the item is relevant to whistleblower protections
- `review_status`: pending, approved, rejected, disputed, corrected
- `reviewer_ids`: at least two reviewers for publication
- `change_log`: visible history of later corrections

Additional provenance rules:

- Do not score based on anonymous submissions.
- Do not score based on screenshots alone when a canonical source URL is available.
- Do not score based on third-party summaries if the underlying official source can be linked directly.
- Treat deleted social content as disputed unless preserved through an approved archival workflow and reviewed by humans.

## Scoring Model Options

### Option 1: Evidence Ledger Only

Show evidence records with filters, but no composite score.

Pros:

- Lowest defamation and bias risk
- Highest explainability
- Easier correction workflow

Cons:

- Less legible to the public
- Less aligned with the original feature pitch

Assessment: this is the only model that is even plausibly compatible with Hush Line's risk profile, and even then it should live outside the core product.

### Option 2: Weighted Rubric Score

Assign points to predefined evidence classes such as:

- named vote on a mapped whistleblower-protection bill
- bill sponsorship or co-sponsorship
- official statement supporting or opposing protections
- repeat conduct after prior notice or correction

Controls required:

- hard cap per evidence type
- no score changes without human approval
- public explanation for each point addition or deduction
- frozen rubric versioning so historical scores remain reproducible

Assessment: technically possible, but high editorial and legal burden.

### Option 3: Real-Time Dynamic Score

Update a public score automatically as new data arrives.

Assessment: not acceptable. It conflicts with required review depth, invites manipulation, and creates correction lag on a politically charged surface.

## Explainability Requirements

Any public judgment system would need these minimum explainability rules:

- Every published claim must link to the underlying evidence item.
- Every evidence item must state whether it reflects a fact, an editorial classification, or an inference.
- Scores must be versioned. A viewer must be able to reconstruct why a score looked a certain way on a certain date.
- Disputed evidence must remain visible as disputed or be fully withdrawn with a public correction note.
- Narrative labels such as "anti-whistleblower" should never be inferred solely from a single vote or isolated quote without documented rubric rules.

## Moderation, Editorial Review, and Correction Workflow

The required workflow is incompatible with a "real-time wall."

Minimum publication workflow:

1. Ingest from allowlisted official sources only.
2. Normalize subject identity and detect duplicates.
3. Create a candidate evidence record with source URL and excerpt.
4. First reviewer classifies relevance to whistleblower protections.
5. Second reviewer confirms attribution, context, and rubric fit.
6. Escalate borderline or defamatory cases to legal/editorial hold.
7. Publish only from an approved batch.
8. Accept corrections through a documented public intake path.
9. Record correction outcome in an immutable revision log.

Operational implications:

- Publication should be batched, not real-time.
- A single engineer is not enough; the bottleneck is editorial review.
- Appeals and correction SLAs would need to be defined before launch.

## Abuse, Harassment, and Platform-Safety Risks

This feature would create strong incentives for hostile use:

- brigading against named officials
- mass-report campaigns using Hush Line's framing as validation
- selective clipping of statements without context
- submission flooding if public evidence uploads are allowed
- retaliatory scrutiny against Hush Line or users during election cycles

Controls that would be mandatory if work were ever reconsidered:

- no public evidence submissions
- no "worst offender" leaderboard
- no shareable attack prompts or one-click campaign copy
- rate-limited publication and moderator tooling
- explicit anti-harassment policy for discussion and correction channels
- human review before any evidence reaches a public page

## Privacy and Security Boundaries for Constituent Outreach

Phase 2 is the clearest no-go area.

Reasons:

- To route users to the correct representative, the product would need address or district data that Hush Line does not need for the whistleblower flow.
- Senate offices explicitly expect constituent contact to include a return postal mailing address, and the House does not provide a central public email list for members.[^senate-contact][^house-contact]
- In-product messaging would create new logging, retention, consent, anti-spam, and abuse-handling responsibilities.
- Asking users to pressure officials from inside a whistleblower platform increases the chance that the product is perceived as advocacy infrastructure rather than secure disclosure infrastructure.

Recommendation for phase 2: do not build constituent contact inside Hush Line. If maintainers ever want action pathways, link out to official office pages from a separate project and do not collect or store constituent-contact data in Hush Line.

## Architecture Options

### Option A: Separate Research Pipeline and Static Publication

Shape:

- scheduled ingesters for official vote feeds and allowlisted official statement sources
- append-only evidence store
- internal review UI
- static export for publication after approval

Pros:

- strongest provenance
- simpler attack surface
- no public write path
- easier rollback and correction

Cons:

- still requires editorial staffing
- still creates legal review burden

Assessment: the only technically plausible architecture if the organization ever pursues adjacent work.

### Option B: In-App Public Scoreboard Backed by Hush Line

Shape:

- live ingestion jobs
- scoring engine
- public ranking pages
- correction and dispute intake
- constituent-action workflows

Assessment: reject. This would repurpose the product into a political publishing system and create ongoing risk that outweighs the feature value.

## Estimated Complexity and Ongoing Burden

| Area                   | Separate research pipeline | In-app real-time wall |
| ---------------------- | -------------------------- | --------------------- |
| Engineering complexity | Medium to High             | Very High             |
| Editorial burden       | High                       | Very High             |
| Legal review burden    | High                       | Very High             |
| Moderation burden      | Medium                     | Very High             |
| Mission fit            | Low to Medium              | Low                   |
| Abuse risk             | Medium                     | Very High             |
| Operational cost       | High                       | Very High             |

Even the narrower option is not "build once." It requires persistent maintenance:

- source monitoring
- parser repair
- identity resolution updates
- dispute handling
- legal review
- rubric governance

## Minimum Viable Scope if the Idea Is Ever Reopened

Only reopen this work under all of these constraints:

- separate project, not core Hush Line product
- official-source evidence only
- federal scope only at first
- no real-time claims
- no numeric public score in an initial release
- no social-media ingestion in the initial release
- no user submissions
- no in-product constituent outreach

Anything broader should be treated as non-viable until the narrow version proves safe and governable.

## Explicitly Non-Viable for an Initial Release

- automated real-time politician scoring
- cross-platform social-media ingestion
- public user-submitted evidence
- one-click constituent campaigns
- storing user address data for office routing inside Hush Line
- ranking politicians by "worst" or "best"

## Final Recommendation

Decision: `Decline`.

Rationale:

- The feature is technically partial but operationally mismatched.
- The most dangerous parts are governance, legal exposure, and abuse incentives, not missing code.
- The feature would pull Hush Line away from the core whistleblower mission and toward political publishing and pressure tooling.
- The proposed phase 2 outreach flow should not exist inside Hush Line.

If maintainers want adjacent work later, open a separate issue for a non-product research artifact with explicit legal review, editorial ownership, and no automated scoring.

## Reference Links Consulted

- [Congress.gov API](https://api.congress.gov/)
- [Library of Congress `api.congress.gov` repository](https://github.com/LibraryOfCongress/api.congress.gov)
- [U.S. Senate: How to Find Congressional Votes](https://www.senate.gov/legislative/HowTo/how_to_votes.htm)
- [U.S. Senate XML Sources Available on Senate.gov](https://www.senate.gov/general/XML.htm)
- [Clerk of the House vote pages](https://clerk.house.gov/Votes)
- [U.S. Senate contact guidance](https://www.senate.gov/senators/How_to_correspond_senators.htm)
- [House find-your-representative guidance](https://www.house.gov/representatives/find-your-representative)
- [IRS restriction of political campaign intervention by section 501(c)(3) organizations](https://www.irs.gov/charities-non-profits/charitable-organizations/restriction-of-political-campaign-intervention-by-section-501c3-tax-exempt-organizations)
- [IRS lobbying guidance for charities](https://www.irs.gov/charities-non-profits/lobbying)
- [X API documentation and pricing](https://developer.x.com/en/docs/twitter-api)
- [X Developer Policy](https://developer.x.com/en/developer-terms/policy.html)
- [YouTube Data API overview](https://developers.google.com/youtube/v3/getting-started)
- [YouTube API quota guidance](https://developers.google.com/youtube/v3/determine_quota_cost)

[^irs-campaign]: IRS guidance says section `501(c)(3)` organizations are absolutely prohibited from participating or intervening in political campaigns on behalf of or in opposition to candidates for elective office.

[^irs-lobbying]: IRS guidance says urging the public to contact legislators regarding legislation can count as lobbying, and excessive lobbying threatens `501(c)(3)` status.

[^senate-votes]: The Senate states that not all votes are roll call votes; voice and division votes do not identify how each member voted.

[^congress-api]: The Congress.gov API repository says the API requires a key, currently uses v3, and is rate-limited to `5,000` requests per hour.

[^congress-api-vote-gap]: This memo infers a practical vote-data gap from the chamber-specific official vote feeds and the Library of Congress API issue tracker, where vote endpoint coverage remains an active topic rather than a settled part of the public API surface.

[^congress-member-issue]: This memo also infers ongoing member-identity complexity from the public Congress API issue tracker, including open discussion about state/district ambiguity in member records over time.

[^senate-contact]: Senate guidance says messages to senators should include a return postal mailing address, and many offices route public-policy correspondence through web forms.

[^house-contact]: House guidance says there is no central listing of public email addresses for members, and users are expected to find and use the individual member website/contact page.
