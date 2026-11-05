# Billing providers and platform independence

Hush Line's core whistleblower application can run without a payment service.
Premium subscription operations use the application-owned `BillingProvider`
interface. The Stripe adapter translates SDK responses into `Customer`,
`SubscriptionEvent`, `InvoiceEvent`, and `BillingEvent` values and translates
provider exceptions into application errors. Routes, premium business logic,
and billing record constructors no longer import Stripe SDK types.

## Configuration

| `BILLING_PROVIDER` | Behavior                                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| Unset              | Preserves existing deployment behavior: Stripe when `STRIPE_SECRET_KEY` is present, otherwise no automated billing. |
| `stripe`           | Existing automated subscriptions; requires `STRIPE_SECRET_KEY`.                                                     |
| `manual`           | Locally administered entitlements, without checkout, payment portal, or webhook routes.                             |
| `none`             | Core application without billing or manual entitlement commands.                                                    |

Unknown providers fail at startup. Manual and disabled modes reject a configured
Stripe secret key, so an accidental provider change cannot silently hide billing
for a deployment still configured to collect payments.

## Self-hosted entitlements

For a deployment without Stripe subscriptions:

1. Set `BILLING_PROVIDER=manual`, omit Stripe credentials, and leave
   `SINGLE_TENANT_ENABLED` disabled.
2. Run the normal database migrations and `flask billing configure` to initialize
   local tiers.
3. Use `flask billing set-tier USER_ID business` to grant an existing account the
   premium entitlement, or `flask billing set-tier USER_ID free` to revoke it.

Run these commands in the application environment, for example with
`docker compose run --rm app poetry run flask billing set-tier 42 business`.
The deployment must pass the selected environment variables into that container.
Only trusted operators with server access can run these commands; no new public
entitlement API is exposed. The command refuses accounts linked to a Stripe
customer or subscription. It does not process payments, fabricate invoices,
mark accounts as paid, or cancel existing subscriptions.

Manual entitlements use the same local tier and feature-limit checks as premium
accounts. Operators can fund the deployment separately, or administer access
without charging recipients. This is a working open-source alternative for
entitlement administration, not an automated card-payment replacement.

## Stripe compatibility

Existing deployments need no new configuration. Checkout parameters, automatic
tax, customer address collection, portal flows, cancellation behavior, webhook
signature validation, and durable event deduplication are retained. Existing
database table and column names containing `stripe` are retained to avoid a
billing-data migration. They are historical persistence names, not SDK types.

The waiting page polls Hush Line's authenticated status endpoint using local
JavaScript. Its unused Stripe.js import has been removed, along with permission
to load Stripe scripts, frames, and API connections. Hosted checkout and portal
redirect destinations remain allowed for the Stripe provider.

Do not switch a running Stripe deployment to manual mode as a cancellation or
migration procedure. Removing credentials does not stop Stripe from billing
customers. Existing subscriptions and pending events must be reconciled before
any operational migration; automatic provider migration is not implemented.

## Scope and extending providers

Implement `BillingProvider` and register its configuration choice in
`hushline/billing/__init__.py`. The implementation must return application values,
authenticate callbacks before queueing them, and declare only the browser
destinations it actually needs. Provider replacement must include tests for
checkout, receipts, cancellation, event processing, and account ownership.

The optional managed Single Tenant provisioning service remains Stripe-specific.
Its independently verified annual-payment proofs, registration promotions,
provisioning authority, and reconciliation are not replaced by manual premium
entitlements. Manual/disabled billing with that service enabled fails at startup.
Self-hosting the whistleblower application does not require that managed service.
We do not claim a drop-in open payment processor for the managed service.

## Verification before deployment

Regression tests exercise the Stripe adapter and existing premium and Single
Tenant flows, signed/tampered/expired webhook payloads, provider configuration,
manual entitlement grants/revocations, and restrictive CSP. SDK calls in these
tests are mocked; they are not evidence of a live payment.

Before deploying, use a dedicated Stripe test-mode environment to complete
checkout, receive signed webhooks, confirm the entitlement and receipt, update
the payment method, disable/re-enable renewal, and cancel. Confirm normal message
submission and inbox access in the same deployment. Never use production payment
credentials for this verification. Run the manual-mode tests without Stripe
credentials and verify local grant/revoke operations independently.
