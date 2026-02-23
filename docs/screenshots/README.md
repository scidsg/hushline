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
