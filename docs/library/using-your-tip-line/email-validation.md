# Email Validation

Source: <https://hushline.app/library/docs/using-your-tip-line/email-validation/>

Email Validation helps you inspect raw message headers and assess whether an email appears authentic.

## What the tool analyzes

- `DKIM`
- `SPF`
- `DMARC`
- domain alignment
- DKIM signing-key records fetched from DNS

## How to use it

1. Copy the raw headers from the email you want to inspect.
2. Paste them into the Email Validation form.
3. Review the validation summary, trust-chain notes, and header context.
4. Download the report if you want a ZIP artifact for later reference.

## What the report includes

- an executive summary
- authentication-result breakdowns
- DKIM signature details
- DKIM key lookups
- warnings and interpretation notes

## Important caution

Older emails can look suspicious even when they were legitimate at the time, especially if DKIM keys were rotated or removed later. Treat the tool as an aid to judgment, not a substitute for context.

## Related docs

- [Tools](./tools.md)
- [Vision Assistant](./vision-assistant.md)
