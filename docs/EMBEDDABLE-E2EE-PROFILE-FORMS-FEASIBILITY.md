# Embeddable E2EE Profile Forms Feasibility Study

Last updated: 2026-05-03

This study evaluates whether Hush Line should support embeddable profile forms on recipient-controlled websites. It is a feasibility study only. It is not approval to implement embeds, relax Hush Line's current framing protections, or trust arbitrary third-party JavaScript with plaintext disclosure content.

## Recommendation

Recommendation: `Proceed with a restricted hosted iframe embed`, gated behind explicit administrator controls and recipient opt-in for eligible profiles.

The preferred path is a Hush Line-hosted embed endpoint that renders a minimal intake form in a sandboxed iframe. The form, JavaScript, CSRF token, CAPTCHA, custom fields, client-side E2EE bundle, submission POST, success state, and no-JS fallback should all remain served by Hush Line. The embedding site should receive only the iframe URL and fixed-size container guidance.

Reject script widgets, static generated forms, and any model where the parent website owns the form DOM or submission JavaScript. Those approaches let the embedding site observe or alter plaintext disclosure content before Hush Line encryption can run.

## Product Fit

Embeds are a good fit for paid Super Users and administrators when the recipient already maintains a higher-trust first-party site, such as a newsroom, law office, nonprofit, school, or security team contact page. They reduce sender friction without requiring the sender to leave a context they already trust.

The fit is weaker for free personal profiles because embeds create new trust, abuse, support, and policy surfaces. A managed service should require Super User eligibility for recipient-controlled embeds. Administrators should be able to enable embeds for their own deployment and for selected profiles without requiring Stripe billing.

Aliases should be eligible, but only when all of the following are true:

- The alias owner is eligible for embeds.
- The alias is not suspended or disabled.
- The alias has a usable recipient encryption target through the owning account's notification recipient/key model.
- The alias has explicit embed opt-in; primary-profile opt-in should not automatically enable aliases.
- If the instance uses verification or caution states, the embedded form must carry the same visible state as the Hush Line-hosted profile.

## Preferred Architecture: Hosted Iframe Embed

Shape:

- New public endpoint such as `/embed/to/<username>` renders an embed-specific profile form.
- The response is served by Hush Line with a narrowly scoped CSP that permits framing only by configured origins for that profile or alias.
- The parent site receives an `<iframe>` snippet, not a script snippet.
- The iframe uses `sandbox` attributes that allow forms and scripts but do not grant same-origin access to the parent.
- The iframe owns the form DOM, CSRF token, CAPTCHA, recipient public keys JSON, client-side encryption bundle, and POST target.
- The iframe success state should show the reply link inside Hush Line-controlled UI and include a clear option to open the reply page in a new top-level Hush Line tab.
- Hush Line should continue to support server-side encryption fallback when JavaScript is unavailable, but the embed should clearly indicate when the sender should open the full Hush Line profile for the strongest experience.

Why this is viable:

- It keeps plaintext disclosure content inside a Hush Line document, not the parent page DOM.
- It preserves the current custom-field and client-side E2EE model, which already renders dynamic message fields and encrypts enabled fields in the browser before submission.
- It lets Hush Line keep CSRF, CAPTCHA, owner-guard, rate limiting, and validation in one code path.
- It can be made compatible with Hush Line's current default `frame-ancestors 'none'` posture by adding a separate embed response policy instead of weakening all pages.

Main limits:

- The parent site can still observe that a visitor loaded the page, the iframe size, coarse timing, scroll context, and whether the iframe URL was requested.
- The parent site can overlay or visually surround the iframe in misleading ways unless Hush Line requires visible Hush Line trust chrome inside the iframe.
- Browser privacy features, tracker blocking, iframe sandboxing, and third-party cookie behavior vary. The embed should not depend on third-party cookies for unauthenticated submission.

## Alternative Architecture: Hosted Redirect With Inline Preview

Shape:

- The recipient's website displays a static Hush Line-branded call-to-action or read-only preview.
- Clicking it opens the normal `/to/<username>` profile in a top-level Hush Line page, preferably with `rel="noopener noreferrer"` and no referrer.
- Optional future enhancement: the recipient can configure a short embed card that shows display name, verification state, and "Send secure tip" button, but no form fields.

Why this is viable:

- It preserves the strongest browser isolation because the sender composes on a top-level Hush Line origin.
- It avoids iframe CSP, sandbox, focus, mobile viewport, and parent-page observation problems.
- It is the safest first release if maintainers want a lower-risk "embed" story before accepting framed submissions.

Main limits:

- It does not meet the full product goal of submitting without navigation.
- It may have less conversion benefit than an inline form.

## Rejected Architectures

### Script Widget

Reject. A script widget would require the recipient site to load Hush Line JavaScript into the parent page or let the parent page host form markup. The parent page could observe keystrokes, replace recipient keys, alter field labels, exfiltrate plaintext before encryption, or remove safety copy. Subresource Integrity does not solve this because the embedding page still controls the DOM around the script and can run its own JavaScript.

### Static Generated Form

Reject for encrypted submissions. A static HTML form could be copied to a recipient site, but it would make key freshness, CSRF, CAPTCHA, custom field updates, server validation, emergency-exit behavior, and E2EE bundle integrity difficult to guarantee. It would also push plaintext handling into an environment Hush Line does not control.

### Cross-Origin API Form

Reject as a sender-facing architecture. A CORS API that accepts encrypted payloads from arbitrary recipient websites would still require recipient-controlled JavaScript to collect plaintext and encrypt it. That breaks the non-goal of trusting arbitrary third-party JavaScript with disclosure content.

### Hybrid Script Plus Hush Line Encryption Worker

Reject for an initial implementation. Moving encryption into a Hush Line worker or isolated frame while the parent owns the visible form is complex and easy to get wrong. The parent can still shape the sender experience, collect duplicate plaintext, and misrepresent what is being sent.

## Threat Model

### Sender

Assets:

- Disclosure content, custom-field answers, contact details, reply link, timing, IP/network metadata, browser fingerprint, and decision to contact a recipient.

Risks:

- The embedding site can log page visits, request timing, referrer context, URL parameters, viewport signals, and analytics identifiers.
- A malicious or compromised embedding page can visually spoof the iframe, place deceptive copy around it, or encourage unsafe disclosures.
- If the parent page can access plaintext DOM or JavaScript state, E2EE is defeated before Hush Line receives the submission.
- A hostile network or employer may correlate the visit to the recipient's site with the iframe request to Hush Line.

Required mitigations:

- Keep plaintext fields inside a Hush Line-origin iframe.
- Do not expose field values through `postMessage`, URL parameters, storage, or parent-readable attributes.
- Set `Referrer-Policy: no-referrer` on Hush Line responses and recommend `referrerpolicy="no-referrer"` on generated iframe snippets.
- Provide visible Hush Line origin, recipient username, verification/caution state, and "open on Hush Line" escape path inside the iframe.

### Embedding Website

Assets:

- Site integrity, editorial reputation, visitor trust, and operational availability.

Risks:

- The site can be compromised and used to mislead senders even if Hush Line remains secure.
- The site may run analytics, heatmaps, session replay, tag managers, or A/B testing that collect sensitive context around the iframe.
- The site may unintentionally create a false authenticity signal for a recipient that Hush Line has not verified.

Required mitigations:

- Embeds should be origin-allowlisted per profile or alias.
- Generated snippets should document that analytics/session replay must not wrap or instrument the intake area.
- Verification and caution state must come from Hush Line, not the parent site.

### Hush Line

Assets:

- Submission confidentiality, integrity, availability, recipient keys, CSRF/session protections, anti-abuse controls, and brand trust.

Risks:

- Relaxing global `frame-ancestors 'none'` or `X-Frame-Options: DENY` could weaken anti-clickjacking protections across the app.
- CORS or API expansion could create new cross-site submission or metadata leakage paths.
- Embed endpoints could become high-volume abuse targets.
- Misconfigured allowlists could allow hostile domains to frame recipient forms.

Required mitigations:

- Add a dedicated embed endpoint with dedicated security headers; do not broaden framing for normal pages.
- Do not enable broad CORS. Form POSTs should stay same-origin from the Hush Line iframe.
- Keep CSRF validation, math CAPTCHA, owner-guard signatures, server validation, and server-side encryption fallback.
- Add rate limiting per profile, per source IP/network bucket, and per deployment.
- Log operational events without disclosure content, field values, reply slugs, full referrers, or analytics identifiers.

### Recipient

Assets:

- Authenticity, profile configuration, custom fields, aliases, inbox integrity, notification settings, and public trust.

Risks:

- A recipient may embed a form on a domain they do not control or later lose control of.
- Aliases may be embedded in the wrong organizational context.
- Brand customization may hide that the form is Hush Line infrastructure, reducing sender ability to reason about trust.

Required mitigations:

- Require explicit origin allowlists and periodic confirmation.
- Allow profile and alias embed disablement independently.
- Keep a visible Hush Line trust boundary in the iframe.
- Show recipient username, display name, verification state, and caution/suspension state inside the Hush Line-controlled frame.

## Security and Privacy Requirements

### Client-Side E2EE

The iframe model can preserve client-side E2EE because the encryption code, recipient public keys, and form fields are all served in a Hush Line-origin document. The implementation must ensure:

- Recipient public keys are loaded from Hush Line, not from parent-page attributes.
- Parent pages cannot pass replacement keys into the iframe.
- `postMessage` is not used for plaintext, ciphertext, keys, field definitions, reply slugs, or validation errors.
- The server-side fallback remains available for no-JS or failed-client-crypto submissions, matching current behavior.
- Existing padding behavior for encrypted fields remains in place to reduce field-length inference.

### Custom Fields

Custom fields are feasible in the iframe because Hush Line already owns field definitions, validation, required/optional state, encrypted/unencrypted flags, and per-alias field configuration. The embed should render the same enabled field set as the Hush Line-hosted profile unless a future product decision adds an explicit "embed field set" configuration.

If a field is configured as not encrypted, the embed must preserve the existing warning and should not allow recipient branding to hide it.

### CSRF, CORS, and Submission Integrity

The iframe should submit to Hush Line same-origin endpoints. It should not require broad CORS because the parent page does not need direct API access.

Implementation should preserve or add tests for:

- Missing or invalid CSRF tokens on embed submissions.
- Owner-guard mismatch if the profile or alias changes while the form is open.
- CAPTCHA failure and rate-limit behavior.
- Rejection when the target has no usable recipient key or is suspended.
- No successful submission when framed from an unapproved origin.

### CSP, Frame Policy, and Clickjacking

The current application sends `frame-ancestors 'none'` and `X-Frame-Options: DENY` globally. A future implementation must keep that default for all non-embed pages.

Embed responses should:

- Set `frame-ancestors` to the exact configured origin list for that profile or alias.
- Avoid wildcard origins.
- Avoid path-based trust; browsers enforce `frame-ancestors` at the origin level.
- Omit `X-Frame-Options` on embed responses only if required for modern `frame-ancestors` compatibility, and test that normal pages still send `DENY`.
- Use a restrictive `sandbox` snippet recommendation such as `allow-forms allow-scripts allow-popups allow-popups-to-escape-sandbox`, adding `allow-same-origin` only if the implementation proves it is required for current client-side encryption and CSRF behavior.
- Keep script sources limited to Hush Line-owned assets and existing approved dependencies.

### Referrer and Metadata Leakage

An embed cannot make sender activity invisible to the parent site. The parent can know that a visitor loaded the page and can infer interaction from timing and layout changes. Hush Line can still reduce leakage:

- Keep `Referrer-Policy: no-referrer`.
- Generate iframe snippets with `referrerpolicy="no-referrer"` because Hush Line's response headers cannot suppress the initial iframe request's referrer on their own.
- Treat parent cooperation as helpful but not sufficient; a hostile or modified parent page can remove the iframe attribute.
- Avoid putting usernames, field names, disclosure subjects, campaign names, or sender-specific values in query strings.
- Do not send parent URL, title, analytics IDs, or arbitrary metadata to Hush Line.
- Use fixed or bounded iframe sizing where possible so height changes do not reveal which field validation path occurred.
- Do not expose reply slugs to the parent page.

### Logging and Analytics

Hush Line should not add third-party analytics to embed pages. Embed logs should be operational only and should avoid:

- Disclosure content.
- Custom-field values.
- Reply slugs or one-time links.
- Full referrers.
- Parent-page titles or analytics identifiers.
- Sender-provided contact details outside the encrypted message body.

Administrators should be able to monitor aggregate embed enablement and abuse counters without per-submission sensitive metadata.

## UX, Accessibility, and Safety Requirements

### Authenticity and Branding

The embedded form must remain visibly Hush Line. Recipients may customize display name, bio, profile fields, primary color, and custom intake questions within existing settings, but they should not be able to remove:

- Hush Line name or deployment name.
- Recipient username.
- Verified, admin, caution, or suspended states.
- Encryption state labels.
- "Open on Hush Line" link.
- Safety and emergency-exit controls.

This boundary helps senders understand that the parent website is not the cryptographic trust boundary.

### Emergency Exit

Emergency-exit behavior must work inside an iframe and should also provide a top-level escape option. A future implementation should test:

- Keyboard access to emergency exit controls inside the frame.
- Whether the control navigates only the iframe or can open a safer top-level destination.
- Behavior under iframe sandbox restrictions.
- Mobile viewport behavior where the iframe may be partially visible.

### No-JS Fallback

No-JS behavior should not silently degrade into an unsafe custom-site form. If JavaScript is unavailable, the iframe should either:

- Submit through the same Hush Line server-side fallback path used by the normal profile form, or
- Present a Hush Line-hosted link to open the full profile in a top-level page.

Which path is acceptable depends on whether CSRF/session and CAPTCHA behavior can be made reliable under modern third-party iframe restrictions.

### Accessibility and Mobile Usability

Embed UI must meet the same accessibility bar as first-party Hush Line pages. Future tests should cover:

- Keyboard-only completion inside the iframe.
- Screen-reader labels and frame title.
- Visible focus states that are not clipped by iframe dimensions.
- Error summaries that remain in-frame and are announced.
- Mobile widths down to small phones.
- High zoom and reduced-motion settings.
- Container sizing that does not hide required fields, CAPTCHA, or submit state.

## Admin and Recipient Controls

Future implementation should include:

- Global admin setting: embeds disabled by default.
- Per-profile setting: primary profile embed opt-in.
- Per-alias setting: alias embed opt-in independent of primary profile.
- Origin allowlist per profile or alias.
- Optional global origin allowlist/denylist for managed and single-tenant operators.
- Ability for admins to disable embeds for any profile or alias.
- Ability to regenerate or revoke an embed token if tokens are used.
- Audit trail for enable/disable and origin changes, excluding disclosure content.

Open product question: whether verified status should be required before managed-service embeds are allowed. The safer default is to allow only verified profiles and aliases on managed SaaS, while allowing instance administrators to choose local policy on single-tenant or personal deployments.

## Deployment Compatibility

### Managed SaaS

Viable with the strictest defaults: Super User or admin eligibility, embeds disabled by default, verified profile recommended or required, per-origin allowlists, central abuse monitoring, and conservative branding boundaries.

### Managed PaaS / Single-Tenant

Viable. Instance operators may need broader policy controls because all recipients may belong to the same organization. Admins should be able to enable embeds without Stripe billing while still preserving per-profile and per-alias opt-in.

### Personal Server

Technically viable but lower priority. Operators may want to embed their own form on a personal site, but framing and domain configuration are easy to misconfigure. Documentation should recommend the hosted redirect model unless the operator understands origin allowlists, HTTPS, onion behavior, and CSP.

## Required Future Changes

Product:

- Define eligibility for managed SaaS, single-tenant, personal server, primary profiles, and aliases.
- Decide whether managed-service embeds require verification.
- Define recipient-facing copy for embed settings and generated snippets.
- Define allowed branding customization and required Hush Line trust chrome.

Backend:

- Add embed enablement and origin allowlist data model.
- Add admin and recipient settings routes.
- Add dedicated embed render and submit handling or a safe shared profile handler mode.
- Add response-specific CSP/frame headers without weakening normal pages.
- Add rate limiting and abuse counters for embed endpoints.
- Preserve CSRF, CAPTCHA, owner-guard, suspension, and missing-key rejection.

Frontend:

- Add embed-specific template with compact responsive layout.
- Keep client-side encryption in Hush Line-origin code.
- Add emergency-exit behavior that works in framed contexts.
- Add no-JS and failed-client-crypto states.
- Add generated iframe snippet UI in settings.

Documentation:

- Add recipient documentation for safe embed use.
- Add admin documentation for global controls and origin allowlists.
- Add deployment notes for CSP, HTTPS, onion services, and analytics restrictions.
- Update security documentation with embed threat model details once implemented.

Tests:

- CSP/header tests proving normal pages remain non-frameable and embed pages are frameable only by configured origins.
- CSRF and owner-guard tests for embed submissions.
- Client-side encryption regression coverage for embed pages.
- No-JS/server-side fallback coverage.
- Alias eligibility and per-alias opt-in tests.
- Suspension, missing-key, verification/caution display, and disabled-embed tests.
- Accessibility tests for keyboard flow, labels, errors, and mobile layout.
- Logging tests or assertions that disclosure content, field values, reply slugs, and full referrers are not recorded.

## Implementation Sequence

1. Ship hosted redirect snippets first if maintainers want the lowest-risk product increment.
2. Add data model and settings controls for explicit embed eligibility and origin allowlists.
3. Add the hosted iframe endpoint with dedicated frame headers and compact template.
4. Add submission, E2EE, no-JS, and accessibility tests before enabling the feature in production.
5. Pilot on a single managed or single-tenant deployment with embeds disabled by default elsewhere.

## Final Assessment

Embeddable E2EE profile forms are feasible only if Hush Line remains the form origin and cryptographic trust boundary. The hosted iframe model is the strongest path that satisfies the product goal while preserving sender confidentiality and the existing E2EE flow. The hosted redirect model is safer and simpler, but it does not fully satisfy inline submission.

Any approach that lets the embedding website own the visible form DOM, submission JavaScript, recipient key selection, or plaintext handling should be rejected.
