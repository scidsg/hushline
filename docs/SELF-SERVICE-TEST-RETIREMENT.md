# PR #2447 rehearsal retirement

The isolated `self-service-test-2447` rehearsal is retired. PR #2447 is closed;
its workflow was already disabled before retirement. No runs were active.
The workflow is retained as an inert fixture under
`tests/fixtures/archived-workflows/` so the historical ownership, trusted-code,
and teardown guard regression tests remain available. It cannot run from there.

## Cleanup evidence

Each run below completed the recorded-resource absence check and guarded
empty-workspace safe-delete successfully. These are historical cleanup results,
not newly performed cloud operations.

| Order                              | Successful cleanup run                                                         |
| ---------------------------------- | ------------------------------------------------------------------------------ |
| `de44b913bbc22b3ac75d8e5b114bdc45` | [Run 37262079957](https://github.com/scidsg/hushline/actions/runs/37262079957) |
| `d9a565c4b17aca835b1f23a0b69b482b` | [Run 37243469653](https://github.com/scidsg/hushline/actions/runs/37243469653) |
| `1c08c360da985ca24e9e246371ffc97f` | [Run 37257528500](https://github.com/scidsg/hushline/actions/runs/37257528500) |
| `d9096a7ac4a4a90198550588df08fdcd` | [Run 37388895031](https://github.com/scidsg/hushline/actions/runs/37388895031) |
| `6368ab5a5987358f9a9083f8ec2707b7` | [Run 37509284407](https://github.com/scidsg/hushline/actions/runs/37509284407) |

The GitHub environment and its three legacy secret copies (SMTP username, SMTP
password, and Stripe test key) are removed. Deployment records remain historical
and are marked inactive with their original log links; failed run conclusions
are preserved. Shared staging, production, and the paid customer lifecycle use
their existing independent configuration. No provider resources or credentials
were deleted as part of this GitHub retirement.

A fresh Terraform inventory was attempted on 2026-10-09, but the existing
production API credential returned HTTP 401. Workspace cleanup evidence above
comes from the successful guarded cleanup jobs, not that unauthorized response.
The dedicated customer cloud inventory is separate and is not proof of staging
resource absence. Any future infrastructure audit must use authorized staging
access; do not restore this retired workflow to perform it.
