# Embeddable E2EE Profile Forms MVP Epic and Child Issues

Source feasibility study: [Embeddable E2EE profile forms feasibility study](./EMBEDDABLE-E2EE-PROFILE-FORMS-FEASIBILITY.md)

This artifact turns the feasibility study into a GitHub epic and scoped child issues for an MVP. The work should use GitHub parent-child issue relationships when creating the issues. If the parent-child field is unavailable, each child issue body should include `Parent epic: #<epic-number>` and the epic should include a linked checklist of child issues.

## Epic: Embeddable Hush Line Profile Forms MVP

### Goal

Implement an MVP for embeddable Hush Line profile forms using the restricted hosted iframe architecture recommended in the feasibility study.

### MVP Direction

- Use a Hush Line-hosted iframe endpoint for inline submissions.
- Keep form DOM, CSRF token, CAPTCHA, custom fields, recipient keys, E2EE JavaScript, submission POST, success state, and no-JS fallback on the Hush Line origin.
- Reject script widgets, static generated forms, CORS form APIs, and parent-owned plaintext form DOM for the MVP.
- Keep normal Hush Line pages protected by `frame-ancestors 'none'` and `X-Frame-Options: DENY`; only dedicated embed responses may be frameable by exact configured origins.
- Require administrator enablement and explicit profile or alias opt-in before any embed can be used.

### Child Issues

- Add embed eligibility, opt-in, and origin allowlist model
- Add admin and recipient embed controls and generated iframe snippets
- Add Hush Line-hosted embed form endpoint with dedicated frame headers
- Preserve secure embed submissions with E2EE, CSRF, CAPTCHA, and owner guard
- Harden embed UX for trust chrome, emergency exit, no-JS fallback, accessibility, and mobile
- Add embed documentation, abuse controls, and logging privacy safeguards

### Security and Privacy Requirements

- Do not weaken E2EE defaults or the existing no-JS server-side fallback.
- Do not expose plaintext, ciphertext, field definitions, keys, reply slugs, validation errors, parent URLs, analytics identifiers, or sender-provided values to embedding pages through URL parameters, storage, `postMessage`, or logs.
- Do not broaden CORS for embed submission.
- Use exact origin allowlists; no wildcard or path-based framing trust.
- Preserve CSRF, CAPTCHA, owner-guard, suspension checks, missing-key rejection, rate limiting, and validation.
- Keep Hush Line trust chrome, recipient identity, verification/caution state, encryption state, emergency-exit controls, and an "Open on Hush Line" path visible inside the iframe.

### Done When

- All child issues are implemented and merged through the epic branch flow.
- Security header, E2EE, submission integrity, alias eligibility, accessibility, logging/privacy, and documentation coverage are in place.
- Embeds remain disabled by default and can only run for explicitly allowed origins and opted-in eligible recipients.

## Child Issue 1: Add Embed Eligibility, Opt-In, and Origin Allowlist Model

Parent epic: `#<epic-number>`

### Scope

Add the backend data model and policy checks needed before any hosted embed endpoint exists.

### Acceptance Criteria

- Add global embed enablement that is disabled by default.
- Add per-primary-profile embed opt-in.
- Add per-alias embed opt-in that does not inherit from the primary profile.
- Add exact-origin allowlists for each eligible profile or alias.
- Support administrator disablement for any profile or alias.
- Reject wildcard origins, path-based origin rules, and invalid schemes.
- Keep aliases eligible only when the owner is eligible, the alias is active, the alias has explicit opt-in, and a usable recipient encryption target exists.
- Preserve existing suspension and missing-key rejection behavior.

### Tests

- Model or route tests cover default disabled state, opt-in requirements, alias independence, invalid origins, wildcard rejection, and missing-key/suspended targets.
- Tests cover that no embed can become active without an exact allowed origin.

### Security Notes

- Do not broaden CORS.
- Do not add fields that store sender data, parent page URLs, analytics identifiers, or disclosure content.

## Child Issue 2: Add Admin and Recipient Embed Controls and Generated Iframe Snippets

Parent epic: `#<epic-number>`

### Scope

Add administrator and recipient-facing controls for enabling embeds and copying a safe hosted iframe snippet.

### Acceptance Criteria

- Admins can enable or disable embeds globally.
- Eligible recipients can opt primary profiles into embeds and manage exact allowed origins.
- Eligible alias owners can opt aliases into embeds independently and manage exact allowed origins.
- The generated snippet uses an iframe, not a script widget.
- The generated snippet includes a safe `sandbox` value, `referrerpolicy="no-referrer"`, a descriptive `title`, and fixed or bounded sizing guidance.
- The UI explains that the parent page must not wrap the intake area in analytics, heatmaps, session replay, or misleading copy.
- The UI does not imply that the parent website is the cryptographic trust boundary.

### Tests

- Admin and settings route tests cover permission boundaries and disabled-by-default behavior.
- Template tests assert iframe snippet attributes and reject script snippets.
- CSP tests confirm normal settings pages remain protected by existing frame restrictions.

### Security Notes

- Do not expose recipient public keys or field definitions through snippet attributes.
- Do not add a parent-page callback, `postMessage` API, or CORS-based submission path.

## Child Issue 3: Add Hush Line-Hosted Embed Form Endpoint With Dedicated Frame Headers

Parent epic: `#<epic-number>`

### Scope

Add the public embed render endpoint and compact form template while preserving default clickjacking protections everywhere else.

### Acceptance Criteria

- Add a public endpoint such as `/embed/to/<username>` for enabled primary profiles and aliases.
- Render the form from the Hush Line origin with Hush Line-owned assets, recipient public keys, CSRF token, CAPTCHA, and custom fields.
- Use a dedicated embed response CSP with `frame-ancestors` set only to the target's exact configured origins.
- Keep `frame-ancestors 'none'` and `X-Frame-Options: DENY` on non-embed pages.
- Omit `X-Frame-Options` only for embed responses if required for `frame-ancestors` compatibility.
- Show Hush Line trust chrome, deployment name, recipient username/display name, verification/caution state, encryption state, emergency-exit controls, and an "Open on Hush Line" link.
- Return a safe denial response when embeds are disabled, the origin list is empty, the target is suspended, or no usable recipient key exists.

### Tests

- Security header tests prove normal pages are non-frameable and embed pages are frameable only by configured origins.
- Route tests cover disabled embeds, missing origin allowlist, unknown/suspended targets, aliases, and missing usable recipient key.
- Template tests cover required trust chrome and no script-widget output.

### Security Notes

- Do not weaken global frame policy.
- Do not allow wildcard origins.
- Do not read parent URL, title, analytics ID, or sender-specific values from query strings.

## Child Issue 4: Preserve Secure Embed Submissions With E2EE, CSRF, CAPTCHA, and Owner Guard

Parent epic: `#<epic-number>`

### Scope

Implement embed submission handling through the existing Hush Line-controlled form path or a safe shared mode that preserves submission integrity.

### Acceptance Criteria

- Embed submissions post to Hush Line same-origin endpoints from inside the iframe.
- Existing client-side E2EE remains the default path for JavaScript-enabled senders.
- Server-side encryption fallback remains available for no-JS or failed-client-crypto submissions when safe under iframe constraints.
- CSRF validation, math CAPTCHA, owner-guard signatures, validation, suspension checks, and missing-key rejection remain enforced.
- Custom fields render and submit with the same enabled field set as the Hush Line-hosted profile unless a later issue adds an explicit embed field set.
- Existing encrypted-field padding behavior remains intact.
- Success state shows the reply link only inside Hush Line-controlled UI and includes an option to open the reply page in a new top-level Hush Line tab.

### Tests

- Submission tests cover valid encrypted embed submissions, no-JS/server-side fallback, missing or invalid CSRF tokens, owner-guard mismatch, CAPTCHA failure, suspended target, and missing key.
- Tests cover custom encrypted and unencrypted fields, including existing warnings for unencrypted fields.
- Tests assert no `postMessage` path exposes plaintext, ciphertext, field definitions, keys, reply slugs, or validation errors.

### Security Notes

- Do not add broad CORS or parent-owned submission APIs.
- Do not put disclosure subjects, field names, sender-provided values, reply slugs, or campaign identifiers in query strings.

## Child Issue 5: Harden Embed UX for Trust Chrome, Emergency Exit, No-JS Fallback, Accessibility, and Mobile

Parent epic: `#<epic-number>`

### Scope

Make the embed experience safe and usable in realistic framed contexts without hiding the Hush Line trust boundary.

### Acceptance Criteria

- The iframe UI remains visibly Hush Line and cannot hide required trust, verification, encryption, caution, suspended, emergency-exit, and "Open on Hush Line" controls.
- Emergency-exit behavior works inside the iframe and offers a top-level escape path when browser and sandbox rules allow it.
- No-JS behavior either uses the same safe server-side fallback path or directs the sender to the full Hush Line profile.
- Error summaries remain inside the frame, are announced accessibly, and do not cause layout shifts that reveal sensitive validation paths to the parent page beyond unavoidable frame interaction.
- Keyboard-only flow works from first focus through submission or safe exit.
- Layout supports mobile widths, high zoom, visible focus states, and reduced motion preferences.

### Tests

- Accessibility tests cover labels, error summaries, focus order, keyboard-only completion, emergency exit, and frame title.
- Responsive tests cover small mobile widths and high zoom enough to prevent clipped required fields, CAPTCHA, submit controls, and error states.
- Security template tests assert required trust chrome cannot be removed by recipient branding settings.

### Security Notes

- Do not allow recipient branding to remove Hush Line identity, recipient identity, verification/caution state, encryption labels, emergency exit, or the open-on-Hush-Line path.
- Do not use parent-page messaging for resizing or validation details in the MVP.

## Child Issue 6: Add Embed Documentation, Abuse Controls, and Logging Privacy Safeguards

Parent epic: `#<epic-number>`

### Scope

Document safe deployment and add operational safeguards that avoid collecting sensitive sender or disclosure data.

### Acceptance Criteria

- Add recipient documentation for safe iframe embed use.
- Add administrator documentation for global enablement, profile and alias opt-in, origin allowlists, verification policy, HTTPS, onion-service considerations, and analytics restrictions.
- Update security or threat-model documentation with embed-specific risks and mitigations.
- Add rate limiting per profile, per source IP/network bucket, and per deployment.
- Add operational abuse counters that do not include disclosure content, custom-field values, reply slugs, full referrers, parent-page titles, analytics identifiers, or sender-provided contact details.
- Document that hosted redirect snippets remain the safer alternative for personal servers or operators that do not understand origin allowlists and CSP.

### Tests

- Logging tests assert disclosure content, custom-field values, reply slugs, full referrers, parent-page titles, analytics identifiers, and sender-provided contact details are not recorded.
- Rate-limit tests cover profile-level and source-level throttling without storing sensitive payloads.
- Documentation link tests cover the new recipient, admin, and security documentation.

### Security Notes

- Logs should be operational only.
- If dependency or CSP scope changes are needed in implementation child issues, document maintainer approval and lock the minimal scope in tests.
