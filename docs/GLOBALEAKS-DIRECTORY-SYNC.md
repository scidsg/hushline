# GlobaLeaks Directory Sync

This repository surfaces GlobaLeaks instances in the Hush Line directory through a checked-in JSON
artifact generated from public GlobaLeaks source pages.

## Data source

- Discovery index: `https://www.globaleaks.org/usecases/`
- Source pages:
  - `https://www.globaleaks.org/usecases/anti-corruption/`
  - `https://www.globaleaks.org/usecases/investigative-journalism/`
- Local artifact: `hushline/data/globaleaks_instances.json`

The refresh code fetches those public pages directly, reuses known enriched rows when the same
instance is still referenced, and emits new rows for newly discovered matching hosts.

## Manual refresh

Run:

```bash
make refresh-globaleaks-listings
```

Optional flags pass through `REFRESH_GLOBALEAKS_ARGS`, for example:

```bash
make refresh-globaleaks-listings REFRESH_GLOBALEAKS_ARGS="--check"
```

## Scheduled refresh

- Workflow: `.github/workflows/globaleaks-directory-refresh.yml`
- Trigger: daily cron + manual dispatch.
- Behavior: refreshes the local artifact from the public GlobaLeaks source pages and opens or
  updates a PR when data changes.

## Current model

- The checked-in artifact is the source of truth and is loaded at runtime, similar to other
  directory-backed listing types.
- Listing pages are read-only and must not imply that the destination is operated by Hush Line.
- If discovery finds no listings at all, the refresh fails closed instead of wiping the artifact.

## Follow-up

- Expand discovery coverage if GlobaLeaks publishes additional public source pages worth ingesting.
- Determine whether we need more metadata, for example onion-only versus clearnet-capable.
