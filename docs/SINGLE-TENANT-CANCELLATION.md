# Annual Single Tenant cancellation

Cancellation stops renewal. The instance remains available through the full
prepaid annual term. At the recorded UTC period end, the instance and its stored
messages are deleted with no export grace period. Cancelling must clearly explain
this data loss and require confirmation. The owner may withdraw cancellation
before the period ends. Cancelling is not immediate account or instance deletion.

## Disposable test implementation

The isolated Stripe sandbox controller uses verified `stripe_test` annual terms.
Its paid Checkout Session reserves a unique order ID in Stripe metadata. A separate
`stripe-deploy` job responds only to a changed `.self-service-stripe.json` pointer
on PR 2447. It independently checks Stripe's test API before creating a workspace
and again before applying the saved create-only plan. The immutable private order
must remain unchanged. This path cannot reuse the original or fixture payment
receipts and does not modify their provisioning pointer.

For a Stripe-backed cancellation, the controller updates `cancel_at_period_end`
and records cancellation without shortening the paid year. Retirement rechecks
the exact Stripe receipt, customer, subscription, paid invoice, annual price
components and recorded period. Stripe must confirm cancellation and real UTC
expiry; a browser redirect or local date edit cannot authorize deletion.
Renewal and cancellation webhooks are signed, with authoritative API reads to
handle replay and event ordering. A paid renewal cannot reactivate a retired order.
The added verification key exists only in `self-service-test-2447`; live keys and
live events are rejected. Production environments and policies are unchanged.

The onboarding controller persists simulated checkout receipts and annual terms
separately from provisioning progress. A server-side worker claims cancelled,
expired terms atomically, once, then publishes a signed private cancellation
record and an immutable public pointer. Uncancelled terms are never submitted.
The worker resumes monitoring after restart; it does not blindly replay an
uncertain or partially completed destructive operation.

The `retire` job is separate from PR-close/label-removal cleanup and only responds
to a changed retirement pointer, so unrelated commits cannot replay a deletion. It runs without
customer deployment review in the existing `self-service-test-2447` environment.
An absent pointer disables every private/cloud step. A present pointer must
identify the original `hushline.foo` order, the explicitly authorized
disposable fixture, or an independently verified Stripe sandbox order; the real workflow clock must show that
the full annual term has ended. Before applying, it rereads the latest private
cancellation and requires an unchanged record. Two saved plans delete only the
recorded resource IDs: first the app, database, and firewall, then the empty
project. The project plan is refreshed after the provider confirms the app and
database are absent and the project contains no resources. This avoids the pinned
provider attempting to move already deleted resources into its default project.
Neither plan permits replacements, imports, additional resources, or changes to
other workspaces. Recovery accepts only the same recorded empty project or an
empty state with every recorded resource confirmed absent; other partial states
are blocked. Workspace removal uses safe-delete only after its state is empty and
all provider resources are confirmed absent. Claim material is not regenerated.

The original instance is never deleted as part of validation. In particular, an old
test order without annual billing dates must not be assigned an inferred expiry
from a deployment timestamp. Its test-only annual term can be explicitly created
starting now, clearly marked simulated, to exercise cancellation without early
deletion. Never backdate this term to force a live teardown.

## Payment integration boundary

Payments remain simulated. Before real checkout is enabled, verified payment
events must create and update the authoritative annual term, synchronize
cancel-at-period-end with the billing provider, and extend the term on a confirmed
renewal. Duplicate and out-of-order events must not shorten a paid period.
The controller's demo registration/session is not production billing identity.

This test job cannot retire production or another tenant. Existing production
client roots retain `prevent_destroy` and their shared mandatory policy. A future
production lifecycle needs its own scoped authorization and policy design; this
change does not weaken or detach any existing policy. The user explicitly authorized creating and deleting one isolated fixture
(`d9a565c4b17aca835b1f23a0b69b482b`) in HushLineDev. It has a synthetic historical
annual term in a separate controller database; it cannot claim a customer domain
or adopt an existing workspace, resource, branch, project, or SMTP identity. Its
receipt cannot be bound to a customer order. The create-only plan guard and normal
annual-expiry delete-only guard both apply. Original state and app-spec fingerprints
are compared before/after each operation. The real workflow clock is never
overridden. Provider absence is verified after deletion. This authorization does
not permit deleting the original test instance. The controller must stay running for its 60-second expiry scan; it
resumes outstanding work on restart. Provider/workflow time adds to the interval
between the paid-period boundary and completed deletion.

## Validation

Focused tests cover annual/leap-day boundaries, early deletion rejection,
cancellation withdrawal, ownership, receipt adoption, stale provisioning writes,
CSRF/CSP, once-only dispatch, restart monitoring, failed teardown containment,
changed private cancellation, and an absent retirement pointer. Existing
ownership tests cover foreign resources, replacements, partial plans, and
nonempty workspace deletion rejection. Local fixtures mock cloud operations;
never pass a test clock to a real teardown workflow. The synthetic fixture receipt
is confined to the newly authorized disposable fixture and never backdates an
existing customer order.

## Fresh browser-driven first attempt

The retired d9a565c4b17aca835b1f23a0b69b482b fixture cannot be recreated. The next
explicitly authorized order is 1c08c360da985ca24e9e246371ffc97f. Its creation job
responds only to a changed `.self-service-lifecycle-fixture.json` pointer after
simulated checkout and an explicit browser provisioning request. Unrelated
commits and the old fixture label cannot create resources. The payment contract
is private and immutable, scoped to one fresh namespace, and checked again before
applying. No infrastructure is created during server preparation.

Its separate controller gives checkout a complete synthetic annual term ending
two hours later (the leap-day edge moves to March 1). The real workflow clock
and full-year validation remain intact. Cancellation and both teardown guards
require the same receipt and dates as checkout. There is no date-edit or general
backdate route. First-attempt success requires both saved-plan deletion phases
to run successfully; project-only recovery cannot qualify. Failed requests are
not replayed and no replacement is permitted. Provider health and original state
fingerprints must pass after creation and after deletion.
