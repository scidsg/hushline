# SecureDrop Directory Sync

This repository mirrors SecureDrop instances into the Hush Line directory using the official SecureDrop directory API.

## Data source

- Directory API: `https://securedrop.org/api/v1/directory/`
- Local artifact: `hushline/data/securedrop_directory_instances.json`

## Manual refresh

Run:

```bash
make refresh-securedrop-listings
```

Optional flags pass through `REFRESH_SECUREDROP_ARGS`, for example:

```bash
make refresh-securedrop-listings REFRESH_SECUREDROP_ARGS="--check"
```

## Scheduled refresh

- Workflow: `.github/workflows/securedrop-directory-refresh.yml`
- Trigger: daily cron + manual dispatch.
- Behavior: refreshes the local artifact and opens/updates a PR when data changes.
