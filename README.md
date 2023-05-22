# Hush Line
[Hush Line](https://hushline.app) is a self-hosted, lightweight private tip line and anonymous suggestion box. Journalists and newsrooms can use Hush Line to give the public an easy way to submit anonymous tips. Educators and schools can use Hush Line to provide students with a safe way to send a message to an adult they trust. And workplaces can use it by Boards of Directors and senior executives hosting a Hush Line instance and providing employees a trustworthy way to securely report ethical or legal issues without revealing their identities.

Hush Line uses your PGP key to encrypt messages, Tor for privacy, HTTPS for secure data transmission, and SMTP for email. Your server will even be configured to scrub visitors' IP addresses. For deployments to public websites, we incorporate a technique known as onion binding, which "associates registered domain names with onion addresses. These associations are established in TLS certificates, making them publicly enumerable in append-only CT logs. &#91;[1](#references)&#93;"

[Click here for a full installation tutorial.](https://scidsg.medium.com/installing-and-configuring-hush-line-on-a-raspberry-pi-daefc3865020)

![hush-cover](https://github.com/scidsg/hush-line/assets/28545431/fe633078-8c93-4953-9de7-b02b5a229c27)

## Easy Install
👉 We recommend using a Gmail account with a one-time password since we store passwords in plaintext.
Your messages are encrypted, so Google won't be able to read their contents.

### Tor + Public Web
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/install.sh | bash
```

### Tor-Only
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/install-tor-only.sh | bash
```

## Add a Display to Your Pi Server
When hosted on a Raspberry Pi, you can optionally add an e-ink display that makes it easy for people in your phycial location to discover and access your Hush Line. Teachers can place one on their desks in a classroom, a school can host one in the common area where students gather, or a manager can have one in a team's collaboration space. 

```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/waveshare-2_7in-eink-display.sh | bash
```

Supported model:
* [waveshare 2.7" E-Paper Display HAT](https://www.waveshare.com/2.7inch-e-paper-hat.htm) (Recommended)

![display-demo](https://github.com/scidsg/hush-line/assets/28545431/ffa0b88d-7b6d-42c1-9323-3fc581b9552d)

## Hush Line Go
Now that your Hush Line server is online you can add a device that that you can take with you when you're on the go. Clip it to your bag, carry it on a keychain, or wear it around your neck. Ready to get started? [Head to the Hush Line Go repository](https://github.com/scidsg/hush-line-go/tree/main).

![238079003-4b91ff4b-53f0-4be8-b8ec-f5f94361fbd8](https://github.com/scidsg/hush-line/assets/28545431/a88fb6cf-c6f1-4e75-9f0a-af59def365cc)

## References
1. https://www.sauteed-onions.org/
