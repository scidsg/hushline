# Documentation Screenshots

This folder stores generated screenshot sets for docs.
Captures are generated from local app state using scripted scenes.
Release automation generates `captureFiles` from images referenced in docs and website surfaces before capture.
Manifests can list `captureFiles`; an empty list captures no images, and an omitted field captures every matching scene target.
Without `captureFiles`, each scene captures both light and dark mode by default.
Without `captureFiles`, each scene captures above-the-fold, then viewport-by-viewport scroll windows, and full-page by default.
Full-page capture is skipped when unsupported.
Each release stores images by session under `releases/<version>/<session>/`.

## Latest run

- Release key: `one-off-directory`
- Base URL: `http://localhost:8080`
- Path: [releases/one-off-directory/README.md](./releases/one-off-directory/README.md)
- Latest alias: [releases/latest/README.md](./releases/latest/README.md)

## Featured Directory

![Directory featured carousel](./releases/latest/guest/guest-directory-featured-carousel-desktop-light-fold.png)

## Profiles

![Art Vandelay profile mobile](./releases/latest/guest/guest-profile-artvandelay-mobile-light-fold.png)

## Conversations

![Conversation inbox](./releases/latest/artvandelay/auth-artvandelay-inbox-conversations-desktop-light-fold.png)
![Conversation thread](./releases/latest/artvandelay/auth-artvandelay-conversation-thread-desktop-light-fold.png)
![Conversation thread mobile](./releases/latest/artvandelay/auth-artvandelay-conversation-thread-mobile-light-fold.png)
![Conversation thread from Newman](./releases/latest/newman/auth-newman-conversation-thread-desktop-light-fold.png)
![Conversation thread from Newman mobile](./releases/latest/newman/auth-newman-conversation-thread-mobile-light-fold.png)

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
