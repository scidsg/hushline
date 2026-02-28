# Download Your Data

Source: <https://hushline.app/library/docs/using-your-tip-line/download-your-data/>

Hush Line lets you download an export of your account data from `Settings` -> `Advanced`.

## What the export contains

The ZIP export includes CSV snapshots of your account data, including:

- `users`
- `usernames`
- `messages`
- `field_definitions`
- `field_values`
- `message_status_text`
- `authentication_logs`

If your account has encrypted PGP message fields, those armored message files are also included separately.

## Optional encrypted export

If your account already has a PGP key, you can encrypt the full export with that key before download. In that case the file is downloaded as a `.zip.asc` artifact instead of a plain ZIP.

## When to use it

- personal backup
- transfer or migration work
- recordkeeping
- review outside the web UI

## Related docs

- [Reading Messages](./reading-messages.md)
- [Message Statuses](./message-statuses.md)
