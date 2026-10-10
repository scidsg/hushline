# Release deployment

Publishing a stable Hush Line release is the maintainer's explicit approval to
deploy it. The existing `make release` process and its registered YubiKey
authorization remain unchanged. There is no second Terraform confirmation step
for a normal release.

The **Deploy published release** workflow runs after release publication or a
successful release image build. It verifies a human administrator published the
latest stable release, its source commit has a remotely verified signature and
belongs to `main`, and the exact tagged image build succeeded.

Automation updates `hushline-env/hushline.tf` on a branch named for the version,
such as `v0.7.29`, using reviewed infra `main` as its base. A generated branch has
only the image version and verified build digest change and a remotely verified signed commit. Existing
branches are checked before reuse and are never reset or force-pushed.
Infrastructure validation must pass before promotion.
Both secret-bearing Python commands run in isolated mode, excluding repository
directories, user site packages, and `PYTHONPATH` from import resolution. The
image-artifact helper is loaded by its exact sibling file path without importing
the repository's `scripts` package. All Python files under `scripts/` are
administrator-governed release dependencies, including added or renamed modules.
The infra repository's **Release branch updates** ruleset restricts changes to
`v*` branches to repository administrators, including the registered publishing
service. Default-branch review rules remain unchanged.

The workflow compares production Terraform inputs with the last applied revision
and blocks pending infrastructure changes. It switches only
`science-and-design/prod` to that version branch, keeps workspace-wide auto-apply
disabled, and automatically confirms only that exact VCS release run. Terraform
still plans the change and enforces configured policies and run tasks, including
protections against app and database deletion. The actual plan must update only
the app's Hush Line image digests; changes to secrets, resources, component counts,
or other app configuration stop automatic confirmation. API/CLI runs and other
VCS runs are not automatically confirmed. Plan JSON stays in memory and is never
logged or written to an artifact.
Infrastructure changes outside a normal image release continue through reviewed
infra pull requests. The release automation does not merge infrastructure PRs or
change branch protections.

Before the first digest-pinned release, deploy the reviewed infra digest-support
change separately. Its `app_image_digest = null` preserves the existing deployed
tag. The automatic app release must not include this module change as an
unrelated infrastructure delta. After that one-time infrastructure preparation,
publishing a stable app release remains the only human release approval.

Once production actually serves the new version, the existing Single Tenant
controller verifies it and queues upgrades for active managed instances to the
same immutable image digest. Each order retains its ownership, payment checks,
resources, private configuration and administrator claim. Cancelled or retiring
instances are not recreated. DIY instances require their operators to update.

## Automation credentials

These repository Actions secrets are used only by the release automation:

- `ADMIN_PAT`: reads release-author permissions and verified commit/build metadata.
- `HUSHLINE_INFRA_STAGING_PAT`: existing infra repository publishing credential.
- `HUSHLINE_INFRA_RELEASE_SIGNING_KEY`: registered service SSH signing identity;
  the workflow creates a private temporary file and removes it after use.
- `HUSHLINE_PRODUCTION_TF_TOKEN`: production Terraform control-plane credential.

The release workflow never uses customer or ephemeral staging Terraform or
DigitalOcean credentials. Rotate credentials before expiration. Missing or invalid
credentials fail deployment rather than falling back to a different account.

## Monitoring and recovery

After publishing a release, monitor its image build, **Deploy published release**,
the production Terraform run, and managed-instance upgrades. A failed build,
invalid signature, superseded release, existing branch with unexpected changes,
or failed infrastructure validation stops promotion. Resolve the failure and
rerun the workflow; successful promotion is idempotent and cannot select an older
production version. Failed managed upgrades retain their recorded service state
and require operator recovery.
