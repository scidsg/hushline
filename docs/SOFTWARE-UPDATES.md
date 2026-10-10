# Software update notice

Provisioned and DIY instances show **⚠️ Update available** in the footer when a
newer stable Hush Line release is known. The notice appears regardless of the app
name and links to the official release notes. The installed version and existing
branding remain visible. The notice does not install software or change settings.

The server checks the public GitHub latest-release API in a background thread,
at most once every 24 hours per worker. The first page can render before the check
finishes; subsequent pages use the cached result. Page rendering never waits for
GitHub. Failures retry after an hour and preserve any previously known release.
Unknown versions and draft or prerelease releases do not produce a notice.

The request contains no instance hostname, installed version, account, visitor,
message, credentials, or cookies. GitHub sees the server's outbound IP address.
Visitors' browsers do not fetch release information; the existing CSP is unchanged.

Checks default to enabled only when an operator has configured a non-onion
`SERVER_NAME` and no `ONION_HOSTNAME`. With no configured canonical hostname,
or with an onion service configured, checks default to disabled. Incoming Host
headers never authorize outbound checks. Operators
can explicitly set `UPDATE_CHECK_ENABLED=true` or `UPDATE_CHECK_ENABLED=false`.
Test-mode applications never make these requests. Offline deployments simply
continue rendering their normal footer when no release information is available.

Managed instance owners receive updates through the existing provisioned-instance
release process. DIY operators should read the release notes and update through
their existing installation method, preserving their database and private settings.
