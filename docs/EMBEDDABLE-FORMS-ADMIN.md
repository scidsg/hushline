# Embeddable Forms Administrator Guide

Embeddable forms allow Hush Line profile and alias forms to be framed on recipient-controlled websites. Treat global enablement as a deployment-level decision because framing expands the public submission surface.

## Required Controls

- Keep embeddable forms globally disabled unless the deployment has an operator who can review origins and recipient use.
- Require a currently paid Super User account before allowing a profile or alias embed to become available.
- Require each profile or alias to opt in separately. Alias opt-in should not imply primary-profile opt-in, and primary-profile opt-in should not imply alias opt-in.
- Use exact origin allowlists only, such as `https://tips.example`. Do not allow paths, query strings, fragments, credentials, or wildcards.
- Prefer verified profiles and aliases for embedded intake, especially when the parent site is a newsroom, law office, employer, school, or organizer site.
- Require HTTPS for clearnet parent pages. Onion-service deployments should use onion origins deliberately and should not mix clearnet and onion embedding unless the operator has reviewed sender expectations and transport behavior.
- Keep analytics away from embedded-intake pages. Do not place session replay, advertising pixels, analytics identifiers, parent-page-title collection, or referrer collection around the iframe.
- Monitor only operational counters. Counters may track attempts, accepted submissions, rejections, and rate-limit events by hashed profile/source labels, but must not include disclosure content, custom-field values, reply slugs, full referrers, parent-page titles, analytics identifiers, or sender contact details.

## Safer Alternative

Hosted redirect links remain the safer default for personal servers and for operators who do not understand origin allowlists, CSP `frame-ancestors`, iframe sandboxing, and no-referrer behavior. A redirect sends the whistleblower to Hush Line's own profile page and keeps the submission flow out of the parent page.

## Operational Safeguards

Hush Line throttles embedded submissions by profile, by source network bucket, and by deployment. Source buckets are logged and stored only as HMAC labels for operational rate limiting. The in-process limiter is an abuse backstop; deployments that run multiple app processes or multiple nodes should still use privacy-preserving edge limits that do not retain sensitive payloads.

Related security details are maintained in the [threat model](./THREAT-MODEL.md#embeddable-profile-forms).
