# Embeddable Forms

Source basis: in-repository embeddable profile form controls and the [embeddable forms administrator guide](../../EMBEDDABLE-FORMS-ADMIN.md).

Embeddable forms let a recipient place a hosted Hush Line submission form on a website they control. Hush Line still serves the form, controls the encryption flow, and returns the reply page after submission.

Use embeds only on pages you control and keep the iframe snippet exactly as Hush Line generates it. The snippet uses a sandbox, disables referrers, and points directly to the hosted Hush Line form. Do not wrap the form with scripts that collect form values, parent-page titles, analytics identifiers, full referrers, or sender contact details.

Before sharing an embedded form:

- Confirm the page domain exactly matches the origin you allowed in Hush Line settings.
- Keep the page available over HTTPS.
- Make sure the recipient profile or alias is verified when senders need a strong identity signal.
- Keep a direct link to the full Hush Line profile nearby so senders can leave the embedded page.
- Do not use embedded forms on pages with invasive analytics, session replay, advertising pixels, or third-party scripts that can observe sender behavior.

For personal servers, temporary sites, or any operator who does not understand origin allowlists and Content Security Policy, use a hosted redirect link instead of an iframe. Redirecting senders to the Hush Line profile is the safer default because it avoids parent-page script, framing, and origin-configuration risks.

## Related Docs

- [Share Your Tip Line](../getting-started/share-your-tip-line.md)
- [Administrator Guide: Embeddable Forms](../../EMBEDDABLE-FORMS-ADMIN.md)
- [Threat Model](../../THREAT-MODEL.md#embeddable-profile-forms)
