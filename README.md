# Hush Line 🤫

[Hush Line](https://hushline.app) is a self-hosted, free and open-source app providing organizations and individuals with a censorship-resistant way to receive private messages from their community. Hush Line fosters trust and builds resilience by putting your community's privacy and security first.

## Easy Install

```bash
curl -sSL https://install.hushline.app | bash
```

Hush Line uses your public PGP key to encrypt messages, Tor for privacy, HTTPS for secure data transmission, and SMTP for email. Your server will even be configured to scrub visitors' IP addresses. For deployments to public websites, we incorporate a technique known as onion binding, which "associates registered domain names with onion addresses. These associations are established in TLS certificates, making them publicly enumerable in append-only CT logs. &#91;[1](#references)&#93;"

[Check out the full installation tutorial on Medium.](https://scidsg.medium.com/installing-and-configuring-hush-line-on-a-raspberry-pi-daefc3865020)

![hush-cover](https://github.com/scidsg/hush-line/assets/28545431/b776d0e0-73a0-4024-b67a-07c4188dd9af)

## Hush Line Go

For increased threat models where someone might want to set up a Hush Line instance without sharing publicly, Hush Line Go is a device you take with you while your server is safely running somewhere else. It checks your server's uptime and displays the same relevant information for submitting a private message. [Head to the Hush Line Go repository](https://github.com/scidsg/hush-line-go/tree/main).

## References

1. https://www.sauteed-onions.org/
