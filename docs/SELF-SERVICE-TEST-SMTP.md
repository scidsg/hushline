# Original test instance SMTP

The original paid test order for `hushline.foo` can receive the dedicated
single-tenant Riseup account through `self-service-smtp-configure` on PR 2447.
This is an in-place application configuration update, not provisioning.

Run `self-service-smtp-inspect` first. It validates the recorded workspace,
project, database, firewall, live application, domain and original source, then
reports only whether SMTP fields exist in the configured and active deployment
specifications. Account notification settings and the enabled existing recipient
must be confirmed in the existing authenticated browser session.

The existing `self-service-test-2447` environment stores the dedicated
`HUSHLINE_SINGLE_TENANT_SMTP_USERNAME` and
`HUSHLINE_SINGLE_TENANT_SMTP_PASSWORD` secrets. Production SMTP credentials must
never be used. Authentication uses Riseup STARTTLS with the application’s existing
default certificate verification. All six runtime routing fields are stored as
platform secrets on the two application services; workers and initialization
commands remain unchanged.

The saved Terraform plan guard requires the exact original four resource IDs,
an application-only in-place update, and only the approved SMTP field values.
It rejects changes to the database, firewall, project, domain, source branch,
initializer, existing secrets and unrelated settings. No review approvals,
replacement resources, invitation resets, DNS changes or cleanup are allowed.
Private variable and plan files must never be uploaded as artifacts.

For delivery verification, resend only the existing harmless test message to
the existing enabled recipient from the original authenticated browser session.
Do not submit a new disclosure. SMTP authentication alone does not establish
message acceptance, and SMTP acceptance does not establish inbox delivery.
