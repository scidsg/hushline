# Specs

Source basis: the public Personal Server docs category and the in-app Personal Server experience described in [server_info.html](../../../hushline/templates/server_info.html).

This page summarizes the operational characteristics that matter when you are using a Hush Line Personal Server.

## Service characteristics

- self-hosted Hush Line deployment
- browser-based receiver workflow
- Tor onion address for anonymous source access
- local-network HTTPS address for nearby administration and receiver use

## First-user behavior

- the first registered user becomes the admin
- after that, normal account setup continues through the standard Hush Line settings flow

## Receiver workflow parity

The Personal Server is still Hush Line. After initial access, the same core receiver tasks apply:

- add a PGP key
- secure the account with a strong password and 2FA
- review messages in the inbox
- manage statuses, notifications, and exports

## Publishing guidance

If your goal is anonymous inbound reporting, publish the onion URL rather than only the local-network address. The local address is helpful for setup, but the onion address is the privacy-preserving endpoint intended for public sharing.
