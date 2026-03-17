# Incremental Flask-WTF/WTForms Modernization Strategy

Study date: March 17, 2026

## Recommendation

Choose Option B: modernize one endpoint at a time, but only after a small Phase 0 foundation is in place.

An app-wide concern-class rewrite is the higher-risk path for Hush Line. The current form surface is concentrated in security-sensitive routes, and the same concern often has different constraints depending on the endpoint:

- settings pages often multiplex several independent forms on one route
- onboarding mixes form validation with step routing and Proton key lookup
- public tip submission uses dynamic fields, CAPTCHA, owner-guard integrity checks, and E2EE-related email behavior

That makes a broad "fix validation everywhere" or "fix rendering everywhere" effort likely to widen the regression blast radius before the new pattern is proven. The safer plan is:

1. Define shared guardrails, helper conventions, and test expectations once.
2. Pilot a low-risk endpoint that still represents the common settings pattern.
3. Roll the proven pattern outward in small PRs, one route at a time.

## Why Not Option A

Option A is still useful, but only as a narrow foundation layer, not as the main migration strategy.

Safe app-wide work:

- add a small submitted-form dispatch helper for routes with multiple forms
- improve test helpers so prefixed forms, subforms, and submit buttons can be posted consistently
- add a template macro or convention for field errors only after a pilot proves the markup contract

Unsafe app-wide work for the first pass:

- replacing route dispatch logic across all settings pages at once
- changing all templates to a new rendering abstraction in one PR
- rewriting dynamic-message or onboarding flows before a simpler route establishes the pattern

## Current State Summary

The codebase already uses `FlaskForm` widely, but the route layer is only partially idiomatic.

Current strengths:

- CSRF protection is consistently wired through `hidden_tag()`
- forms already hold most field definitions and validators
- many critical flows already have route-level tests

Current friction points:

- many multi-form routes still dispatch with `submit.name in request.form`
- some routes mix form validation with raw `request.form.get(...)` branching
- security-critical validation often lives outside the form object and must be preserved explicitly
- templates often render fields manually, which makes field-level error handling inconsistent
- `tests/helpers.py::form_to_data()` works for basic forms but does not model subforms and multi-submit routes well; existing tests already work around that in `tests/test_settings.py`

## Scoring Rubric

Complexity and regression risk are scored from 1 to 5.

- Complexity: number of forms, dynamic fields, network side effects, async helpers, and special dispatch rules
- Regression risk: security/privacy impact, auth/session impact, E2EE impact, and how many user flows depend on the route

## Endpoint Inventory

| Endpoint                                                          | Current pattern                                                                                  | Complexity | Regression risk | Migration value | Recommended phase |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------: | --------------: | --------------: | ----------------- |
| `/settings/auth`                                                  | Two independent forms, `request.form` submit-name dispatch, session reset on password change     |          2 |               3 |               4 | Phase 1 pilot     |
| `/email-headers` and `/email-headers/evidence.zip`                | Single-form validate flow plus export form with hidden field handoff                             |          2 |               2 |               3 | Phase 2           |
| `/settings/replies`                                               | Single form, straightforward persistence, limited branching                                      |          2 |               2 |               2 | Phase 2           |
| `/settings/encryption` and `/settings/update_pgp_key_proton`      | One manual-key form plus Proton lookup route, PGP validation and external fetch                  |          3 |               4 |               3 | Phase 3           |
| `/settings/notifications`                                         | Four forms on one route, nested SMTP subform, PGP/SMTP guardrails, runtime connection validation |          4 |               4 |               5 | Phase 3           |
| `/settings/registration`                                          | Four admin forms on one route, invite-code lifecycle, submit-name dispatch                       |          4 |               3 |               4 | Phase 4           |
| `/settings/branding`                                              | Many admin forms, file upload, delete action, homepage selection, template validation            |          5 |               4 |               4 | Phase 4           |
| `/settings/guidance`                                              | Several admin forms plus indexed dynamic prompt forms and delete/update branching                |          5 |               4 |               4 | Phase 4           |
| `/settings/profile`, `/settings/alias/<id>`, `/settings/*/fields` | Shared helpers, async URL verification, partial field updates, dynamic field builder             |          5 |               5 |               5 | Phase 5           |
| `/register`, `/login`, `/verify-2fa-login`                        | Mostly idiomatic forms, but still mixed with CAPTCHA/session/auth branching                      |          4 |               5 |               4 | Phase 6           |
| `/onboarding`                                                     | Multi-step state machine, mixed forms, Proton fetch, conditional redirects                       |          5 |               5 |               5 | Phase 6           |
| `/to/<username>`                                                  | Dynamic public message form, CAPTCHA, owner-guard signature, E2EE-sensitive email behavior       |          5 |               5 |               5 | Phase 7           |

## Chosen Pilot

Pilot endpoint: `/settings/auth`

Why this is the best first pilot:

- It is small enough to modernize in one PR.
- It exercises the common Hush Line settings shape: multiple forms on one endpoint.
- It has strong existing behavioral coverage for successful username/password changes.
- It is sensitive enough to prove the pattern under real auth/session constraints, but it does not touch PGP, SMTP, onboarding, dynamic fields, or whistleblower message intake.
- The rollback cost is low because the route, template, and tests are tightly scoped.

Keep `/email-headers` as the fallback pilot only if maintainers want a non-settings control sample first. It is lower risk than `/settings/auth`, but it proves less of the settings-specific dispatch pattern that issue #647 is concerned with.

## Approved Multi-Form Route Convention

For any migrated route that renders multiple independent forms on one endpoint, use this pattern:

1. Instantiate every form at the top of the route on both `GET` and `POST`.
2. Select the submitted form once, before validation, by checking the bound submit fields for that route.
3. Validate and handle only the submitted form.
4. Populate default field values only for forms that were not just submitted, so invalid POSTs preserve the user's entered values.
5. Keep request-, session-, database-, crypto-, or network-dependent validation in the route or its dedicated handler, not in a generic dispatch helper.

Minimal route shape:

```python
form_a = FormA()
form_b = FormB()
submitted_form = next(
    (form for form in (form_a, form_b) if form.submit.name in request.form),
    None,
)

if submitted_form is not form_a:
    form_a.field.data = existing_value

status_code = 200
if request.method == "POST":
    if submitted_form is form_a and form_a.validate():
        return handle_form_a(form_a)
    if submitted_form is form_b and form_b.validate():
        return handle_form_b(form_b)
    form_error()
    status_code = existing_invalid_post_status

return render_template(...), status_code
```

Notes:

- The submitted-form selection should stay route-local unless several routes prove they need the exact same helper.
- Routes with multiple submit buttons on one form may still branch on the bound submit fields for that form, but should keep that branching explicit and close to the route handler.
- CSRF handling stays unchanged: each rendered form keeps its own `hidden_tag()` and retains the route's current failure behavior.

## Pilot Implementation Plan

Scope only one route/template/test cluster:

- `hushline/settings/auth.py`
- `hushline/templates/settings/auth.html`
- `tests/test_settings.py`
- `tests/test_settings_common.py`
- `tests/helpers.py` only if the pilot needs a better form-post helper

Implementation steps:

1. Introduce a small, reusable submitted-form selection pattern.
   - Goal: stop branching directly on `request.form` submit-name checks for the pilot route.
   - Prefer checking bound form state, such as which submit field is populated, over ad hoc string checks.
2. Keep each form responsible for its own validation.
   - Username change should only validate the username form.
   - Password change should only validate the password form.
3. Preserve route outcomes exactly.
   - same redirect targets
   - same flash strings
   - same session-clearing behavior after password change
   - same HTTP 400 behavior for invalid submissions
4. Tighten template-field coupling.
   - Render the pilot fields and field errors from the bound WTForms objects only.
   - Do not introduce a large app-wide macro library yet.
5. If test friction appears, add a small helper that can post one named form cleanly.
   - The helper must support submit buttons and subform field names without changing runtime behavior.

Pilot success metrics:

- no direct submit-name dispatch remains in `hushline/settings/auth.py`
- invalid username submissions show only username-form errors
- invalid password submissions show password-form errors and preserve the existing session/logout behavior contract
- existing user-visible copy, redirect targets, and status codes stay unchanged
- the route can serve as a copyable pattern for `/settings/notifications` and `/settings/registration`

## Guardrails

These apply to every migration phase.

- Preserve CSRF behavior exactly. Every migrated form must keep `hidden_tag()` and existing CSRF failure behavior.
- Preserve current UX contracts unless a maintainer explicitly approves a change.
  - flash strings
  - redirect targets
  - response codes on invalid POSTs
  - field names consumed by existing JavaScript, if any
- Keep security-critical checks outside the form object when they depend on runtime state or cryptographic context.
  - CAPTCHA
  - owner-guard signature checks
  - SMTP host safety checks
  - Proton lookup error handling
  - PGP encryptability checks
  - URL verification for profile fields
- Do not move E2EE-sensitive behavior into generic helpers unless tests prove both the JS-enabled and fallback paths still work.
- Do not broaden CSP or introduce inline scripting as part of template cleanup.
- Keep logging discipline unchanged: never log disclosures, PGP keys, or other sensitive payloads.

## Phase Plan

### Phase 0: Foundation

Scope:

- document the approved route pattern
- add or improve a form-post test helper
- define the minimum regression checklist for migrated routes

Estimated effort: 0.5 to 1 day

Backout:

- revert helper additions only
- no user data or schema changes involved

### Phase 1: Pilot `/settings/auth`

Scope:

- modernize route dispatch and template-field coupling for the auth settings page

Estimated effort: 1 day

Backout:

- revert the route, template, and auth-focused tests in one PR rollback

### Phase 2: Simple Single-Form Routes

Scope:

- `/settings/replies`
- `/email-headers`

Estimated effort: 1 to 2 days

Risk notes:

- low auth risk
- useful for proving a simpler rendering pattern before more complex settings pages

Backout:

- revert each endpoint independently

### Phase 3: Security-Aware Settings Routes

Scope:

- `/settings/notifications`
- `/settings/encryption`
- `/settings/update_pgp_key_proton`

Estimated effort: 2 to 4 days

Risk notes:

- touches PGP, SMTP, and notification behavior
- must preserve current generic-notification, include-content, and encrypt-entire-body behavior

Backout:

- migrate one endpoint per PR
- revert the specific endpoint if SMTP or PGP behavior changes unexpectedly

### Phase 4: Admin Multi-Form Routes

Scope:

- `/settings/registration`
- `/settings/branding`
- `/settings/guidance`

Estimated effort: 3 to 5 days

Risk notes:

- many forms on one page
- some actions include deletes, file uploads, or template-setting validation

Backout:

- keep one admin section per PR so rollback remains route-local

### Phase 5: Profile and Alias Settings

Scope:

- `/settings/profile`
- `/settings/alias/<id>`
- `/settings/profile/fields`
- `/settings/alias/<id>/fields`

Estimated effort: 4 to 6 days

Risk notes:

- async URL verification
- partial location updates
- dynamic field builder
- shared helpers used by primary and alias flows

Backout:

- preserve the existing shared helper entry points until the new pattern is fully proven
- revert endpoint groups together if shared-helper changes cannot be isolated

### Phase 6: Auth and Onboarding Core Flows

Scope:

- `/register`
- `/login`
- `/verify-2fa-login`
- `/onboarding`

Estimated effort: 5 to 8 days

Risk notes:

- login, session, CAPTCHA, first-user behavior, invite-code logic, and onboarding completion state

Backout:

- one route family per PR
- stop immediately if response-code or redirect contracts shift

### Phase 7: Public Tip Submission

Scope:

- `/to/<username>`

Estimated effort: 4 to 7 days

Risk notes:

- highest security and privacy sensitivity in the form stack
- dynamic fields and E2EE-sensitive email fallback behavior make this the final migration target

Backout:

- require a dedicated rollback-ready PR
- do not combine this route with unrelated form work

## Required Test Strategy Updates

Before implementation begins on any phase, lock in route contracts first.

## Minimum Regression Checklist

For every migrated endpoint, add or confirm tests for:

- successful POST for each form on the page
- invalid POST returning the same status code as before
- CSRF rejection behavior
- field-level error rendering on the form that was actually submitted
- unchanged redirect target and flash copy for both success and failure paths
- unchanged persistence side effects in the database and session
- unchanged session/auth side effects for routes that log out, rotate session state, or otherwise mutate authentication state
- unchanged runtime guard behavior when validation depends on request/session/crypto/network state
- unchanged CSP posture if templates or static assets are touched

Pilot-specific tests to add before refactoring `/settings/auth`:

- missing-CSRF POST to `/settings/auth`
- invalid username POST asserts username field error rendering and no password-side effect
- invalid password POST asserts password field error rendering and unchanged password hash
- username-form POST does not trigger password-form validation
- password-form POST does not trigger username-form validation

Phase-specific additions:

- `/settings/notifications`: explicitly cover all three notification/email modes and SMTP validation failures
- `/settings/encryption` and Proton lookup: cover invalid key, non-encryptable key, fetch failure, and invalid email cases
- `/settings/profile` and alias flows: cover location normalization, URL verification, and field-builder actions independently
- `/onboarding`: cover per-step invalid POST behavior, completion redirects, and PGP/manual/proton branches
- `/to/<username>`: preserve owner-guard, CAPTCHA, encrypted-field persistence, and server-side full-body email fallback behavior
- any template touched during migration: confirm CSP tests remain green and no inline handlers are introduced

## Decision Summary

Feasibility: yes.

The lowest-risk path is a phased, endpoint-by-endpoint modernization that starts with `/settings/auth`, uses a small shared foundation, and leaves the public whistleblower submission route for last. That approach addresses the maintainability problems raised in issue #647 without taking a single large swing across Hush Line's security-critical form flows.
