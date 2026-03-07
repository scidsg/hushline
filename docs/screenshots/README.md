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

- `build-release.yml` now calls `.github/workflows/docs-screenshots.yml` after the release image push succeeds for a tag.
- `.github/workflows/docs-screenshots.yml` captures screenshots from the tagged release commit and uploads both `releases/<version>/` and `releases/latest/` in an artifact without using the website PAT.
- Manual `Docs Screenshots` runs now treat `release_key` as the checkout ref when `release_ref` is omitted, so backfills follow the requested release tag instead of `main`.
- `build-release.yml` then calls `.github/workflows/publish-docs-screenshots.yml`, which is the only workflow that uses `HUSHLINE_WEBSITE_SCREENSHOTS_PAT` and syncs the latest screenshots plus the `releases/latest/` and `releases/<version>/` archives into `scidsg/hushline-website`.
