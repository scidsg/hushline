# UI Text Audit and Recommendations

Last updated: 2026-02-27

## Scope

This audit reviews user-facing text in:

- `hushline/templates/` (public flows, settings flows, premium, tools)
- `hushline/routes/` flash messages
- `hushline/settings/` flash messages and form labels

This document is recommendations only. No UI text was changed.

## Executive Summary

The current UI voice is generally direct and practical, but inconsistent across flows.

Top issues:

- Emoji-heavy status messaging mixes tone and severity.
- Terminology is inconsistent across core concepts.
- Some CTAs and empty/error states are not actionable.
- A few visible spelling/wording issues reduce trust.
- Some copy drifts into promotional language in security-critical context.

## Findings and Recommendations

### 1. Status tone is inconsistent and emoji-led

Observed patterns:

- Success, warning, and errors are often prefixed with emoji (`👍`, `⛔️`, `💔`, `🔥`, `🎉`).
- Similar events use different emotional tone by location.

Examples:

- `hushline/settings/common.py`
- `hushline/routes/auth.py`
- `hushline/routes/message.py`

Recommendation:

- Standardize message tone to neutral, direct, and action-oriented.
- Use semantic alert styles for severity; reserve emoji for rare, non-critical contexts.
- Keep one pattern per severity:
  - Success: outcome first.
  - Error: failure + next step.
  - Warning: risk + mitigation.

### 2. Terminology is inconsistent across core flows

Observed patterns:

- Mixed use of `tip`, `message`, `tip line`, `profile`, and `directory` phrasing.
- Similar actions are named differently across templates and settings.

Examples:

- `hushline/templates/onboarding.html`
- `hushline/templates/profile.html`
- `hushline/templates/settings/replies.html`

Recommendation:

- Define and enforce a small controlled glossary:
  - `message` for submitted content.
  - `tip line` for the receiver page.
  - `User Directory` for discovery list.
  - `message status` for sender-visible state.
- Apply one preferred term per concept in all user-facing copy.

### 3. CTA text is mixed in specificity

Observed patterns:

- Generic CTAs (`Continue`, `Finish`) next to specific CTAs (`Update PGP Key`, `Download Report`).
- Some destructive/payment actions are short but not explicit enough about impact.

Examples:

- `hushline/templates/onboarding.html`
- `hushline/templates/premium.html`
- `hushline/templates/settings/advanced.html`

Recommendation:

- Use action + object + optional consequence:
  - `Continue to Encryption`
  - `Disable Auto-Renew`
  - `Delete Account Permanently`
- Keep high-risk actions explicit and unambiguous.

### 4. Non-actionable empty/error states

Observed patterns:

- Empty and limit states do not always tell users what to do next.

Examples:

- `hushline/templates/inbox.html` (`Nothing to see here...`)
- `hushline/templates/rate_limit_exceeded.html` (poetic text, no recovery step)

Recommendation:

- Add immediate next step guidance for each state:
  - when to retry
  - where to navigate
  - what condition caused the block

### 5. Trust-impacting wording and spelling defects

Observed patterns:

- Visible typos and wording slips in admin/settings copy.

Examples:

- `hushline/templates/settings/branding.html` (`Diretory Intro Text`)
- `hushline/settings/forms.py` (`Update Visibilty`)
- `hushline/templates/vision.html` (`severs`)

Recommendation:

- Fix high-visibility typos first.
- Add a lightweight copy QA checklist for UI PRs.

### 6. Promotional phrasing appears in operational/security surfaces

Observed patterns:

- Premium and onboarding copy uses promotional framing in places where users are making security/privacy decisions.

Examples:

- `hushline/templates/premium-select-tier.html`
- `hushline/templates/settings/profile.html`

Recommendation:

- Keep security and setup flows factual and low-pressure.
- Separate pricing persuasion from safety and configuration instructions.

### 7. Potentially over-confident promises

Observed patterns:

- Some text implies response expectations not guaranteed by system behavior.

Example:

- `hushline/templates/submission_success.html` (`You should expect a response within a few days.`)

Recommendation:

- Avoid guarantees in receiver-dependent workflows.
- Replace with expectation-safe wording that does not overpromise.

## Proposed Copy Standard

Adopt these principles for all UI text:

1. Clear: one idea per sentence, concrete nouns, minimal jargon.
2. Concise: short labels, short alerts, avoid filler.
3. Actionable: tell users exactly what happened and what to do next.
4. Neutral: no hype, minimal exclamation points, limited emoji use.
5. Safety-first: risks and mitigations are explicit where relevant.

## Priority Backlog

### P0 (high impact, low effort)

- Correct visible typos and wording defects.
- Rewrite destructive-action and security warnings to explicit neutral language.
- Replace non-actionable rate-limit and empty-state text with recovery steps.
- Remove response-time guarantees from submission confirmation.

### P1 (high impact, medium effort)

- Standardize flash message tone and severity patterns across routes/settings.
- Normalize terminology through a shared glossary.
- Make CTA labels consistently specific.

### P2 (medium impact, medium effort)

- Rework premium and onboarding copy to reduce promotional tone in critical setup paths.
- Build a reusable copy checklist for future PR review.

## Sample Rewrites (for future implementation)

These are examples only, not applied in code:

- `⛔️ Invalid username or password.` -> `Invalid username or password.`
- `👍 Message submitted successfully.` -> `Message sent.`
- `🔥 Your account and all related information have been deleted.` -> `Account deleted permanently.`
- `Nothing to see here...` -> `No messages yet. Check back later or share your tip line URL.`
- `Rate Limit Exceeded` poem block -> `Too many requests. Try again in a few minutes.`
