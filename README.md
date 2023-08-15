# Hush Line 🤫

[Hush Line](https://hushline.app) is a free and open-source, self-hosted anonymous tip line that makes it easy for organizations or individuals to install and use. It's intended for journalists and newsrooms to offer a public tip line; by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

## Easy Install

```bash
curl -sSL https://install.hushline.app | bash
```

## System Requirements

### VPS
- **OS:** Debian 11/12 x64

### Raspberry Pi
- **Hardware:** Raspberry Pi 4/3B+
- **OS:** Raspberry Pi OS (64-bit)

Hush Line uses your public PGP key to encrypt messages, Tor for privacy, HTTPS for secure data transmission, and SMTP for email. Your server will even be configured to scrub visitors' IP addresses. For deployments to public websites, we incorporate a technique known as onion binding, which "associates registered domain names with onion addresses. These associations are established in TLS certificates, making them publicly enumerable in append-only CT logs. &#91;[1](#references)&#93;"

Hush Line deploys to either an onion-only instance or Tor + public web. It's a web and email server and a Python app that encrypts a message with your public PGP key once a message gets submitted, then saves it, and finally emails the encrypted message to you. Your data never gets saved in an unencrypted state. And since all messages are sent to your email, you never have to log in to the device.

For install instructions [read the docs](https://github.com/scidsg/hushline/tree/main/docs), or [check out the full tutorial on Medium.](https://scidsg.medium.com/installing-and-configuring-hush-line-on-a-raspberry-pi-daefc3865020)

![hush-cover](https://github.com/scidsg/hush-line/assets/28545431/b776d0e0-73a0-4024-b67a-07c4188dd9af)

## References

1. https://www.sauteed-onions.org/
