# Ephemeral pull-request staging

Ephemeral staging is created only when a maintainer adds the `staging` label to
an internal Hush Line pull request. Production is outside this workflow's scope:
the workflow does not use the production workspace, token, database, DNS name,
onion identity, SMTP or Stripe credentials, or Spaces subscription.

## One-time setup

Create the `ephemeral-staging` GitHub environment and require maintainer approval
for deployments. Add these repository secrets:

- `HUSHLINE_STAGING_TF_TOKEN`: an HCP Terraform token limited to disposable
  workspaces in the `Hush Line Dev` project.
- `HUSHLINE_STAGING_DO_TOKEN`: a distinct staging-only DigitalOcean token with
  only the app, database, firewall, project, region, and size permissions needed
  by `hushline-ephemeral-staging`. Do not grant Spaces permissions and never
  reuse `DIGITALOCEAN_TOKEN` or a production token.
- `HUSHLINE_INFRA_TOKEN`: read-only access to the immutable
  `scidsg/hushline-infra` revision pinned in `staging_deploy.yml`.

Create the `staging` pull-request label. Only users trusted to approve temporary
infrastructure spend should be able to add it.

## Use

1. Add `staging` to an internal pull request.
2. Approve the `ephemeral-staging` GitHub environment deployment.
3. Wait for the workflow to comment with the generated HTTPS and onion URLs.
4. Perform any additional manual checks using synthetic data only.
5. Remove `staging` as soon as testing is complete.
6. Confirm the workflow comments that the Terraform workspace and cloud
   resources were destroyed.

Only one open pull request may hold the label. New commits redeploy that pull
request's environment. The label expires after 24 hours, and HCP Terraform has
an independent 24-hour auto-destroy deadline.

## Automated validation

Before reporting readiness, the workflow verifies:

- the DigitalOcean `/health.json` endpoint;
- the public directory, registration, and login surfaces in Chromium;
- CSP and other security headers without broadening policy;
- secure browser context;
- the disposable v3 onion endpoint through Tor.

The environment uses two 1 GiB clearnet app instances, a 1 GiB internal onion
app, a pinned onion-service worker, and a two-node PostgreSQL 16 managed cluster.
Public blob storage is explicitly disabled, so it creates no Spaces bucket and
receives no Spaces credentials.

## Persistent staging retirement

Do not remove the existing persistent staging environment until the new workflow
has completed two successful create, validate, destroy, and recreate drills.
Retirement is a separate destructive operation requiring an authenticated cloud
inventory and explicit maintainer approval. No retirement plan may reference or
apply the production workspace.
