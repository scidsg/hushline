# Documentation Screenshots

This folder stores generated screenshot sets for docs.
Captures are generated from local app state using scripted scenes.
Each scene captures both light and dark mode by default.
Each scene captures above-the-fold, then viewport-by-viewport scroll windows, and full-page by default.
Full-page capture is skipped when unsupported.
Each release stores images by session under `releases/<version>/<session>/`.

## Latest run

- Release key: `one-off-directory`
- Base URL: `http://localhost:8080`
- Path: [releases/one-off-directory/README.md](./releases/one-off-directory/README.md)
- Latest alias: [releases/latest/README.md](./releases/latest/README.md)

## Required accounts

- admin (admin and org settings scenes)
- artvandelay (authenticated user settings scenes)
- newman (authenticated and onboarding-state settings scenes)
- first-user admin creation scene (captured via a separate manifest on a brand-new instance)

## Regenerate

```sh
make docs-screenshots RELEASE=one-off-directory
make docs-screenshots-first-user RELEASE=one-off-directory
```

