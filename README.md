# Hush Line 🤫

[Hush Line](https://hushline.app) is a self-hosted, lightweight private tip line and anonymous suggestion box. Journalists and newsrooms can use Hush Line to give the public an easy way to submit anonymous tips. Educators and schools can use Hush Line to provide students with a safe way to send a message to an adult they trust. And workplaces can use it by Boards of Directors and senior executives hosting a Hush Line instance and providing employees a trustworthy way to securely report ethical or legal issues without revealing their identities.

## Easy Install

👉 We recommend using a Gmail account with a one-time password since we store passwords in plaintext.
Your messages are encrypted, so Google won't be able to read their contents.

```bash
curl -sSL https://install.hushline.app | bash
```

Hush Line uses your public PGP key to encrypt messages, Tor for privacy, HTTPS for secure data transmission, and SMTP for email. Your server will even be configured to scrub visitors' IP addresses. For deployments to public websites, we incorporate a technique known as onion binding, which "associates registered domain names with onion addresses. These associations are established in TLS certificates, making them publicly enumerable in append-only CT logs. &#91;[1](#references)&#93;"

[Check out the full installation tutorial on Medium.](https://scidsg.medium.com/installing-and-configuring-hush-line-on-a-raspberry-pi-daefc3865020)

![hush-cover](https://github.com/scidsg/hush-line/assets/28545431/204f5d03-2454-4c49-8c5a-a91d3de3f81f)

## Hush Line Go

For increased threat models where someone might want to set up a Hush Line instance without sharing publicly, Hush Line Go is a device you take with you while your server is safely running somewhere else. It checks your server's uptime and displays the same relevant information for submitting a private message. [Head to the Hush Line Go repository](https://github.com/scidsg/hush-line-go/tree/main).

## References

1. https://www.sauteed-onions.org/
