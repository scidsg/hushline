# Documentation Screenshots

This folder stores generated screenshot sets for docs.
Captures are generated from local app state using scripted scenes.
Screenshots are above-the-fold only (viewport capture, no full-page images).
Each release stores images by session under `releases/<version>/<session>/`.

## Latest run

- Release key: `v0.5.53`
- Base URL: `http://localhost:8080`
- Path: [releases/v0.5.53/README.md](./releases/v0.5.53/README.md)
- Latest alias: [releases/latest/README.md](./releases/latest/README.md)

## Required accounts

- admin (admin and org settings scenes)
- artvandelay (authenticated user settings scenes)
- newman (authenticated and onboarding-state settings scenes)

## Regenerate

```sh
make docs-screenshots RELEASE=v0.5.53
```

Release automation note:

- `.github/workflows/docs-screenshots.yml` is the release and manual entrypoint. On published releases it waits for the released GHCR image to exist, captures screenshots from the requested release ref, uploads both `releases/<version>/` and `releases/latest/` in an artifact, and then calls the publish workflow below. Manual `workflow_dispatch` runs use the same capture-and-publish path.
- Manual `Docs Screenshots` runs now treat `release_key` as the checkout ref when `release_ref` is omitted, so backfills follow the requested release tag instead of `main`.
- `.github/workflows/publish-docs-screenshots.yml` is the only workflow that uses the screenshot publishing PATs. It syncs the latest screenshots plus the `releases/latest/` and `releases/<version>/` archives into `scidsg/hushline-website`, and it also updates `scidsg/hushline-screenshots` with the versioned archive plus badge and root README. Both destinations use dedicated automation branches, open or update PRs, and then attempt to merge them immediately.
