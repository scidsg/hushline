# Hush Line 🤫

[Hush Line](https://hushline.app) is a free and open-source, self-hosted anonymous tip line that makes it easy for organizations or individuals to install and use. It's intended for journalists and newsrooms to offer a public tip line; by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

## Easy Install

```bash
curl -sSL https://install.hushline.app | bash
```

To install a 2.7" Waveshare e-Paper display:
```
curl -sSL https://raw.githubusercontent.com/scidsg/hushline/main/scripts/waveshare-2_7in-eink-display.sh | bash
```

## System Requirements

### VPS
- **OS:** Debian 11/12 x64

### Raspberry Pi
- **Hardware:** [Raspberry Pi 4](https://www.amazon.com/Raspberry-Model-2019-Quad-Bluetooth/dp/B07TC2BK1X/?&_encoding=UTF8&tag=scidsg-20&linkCode=ur2&linkId=ee402e41cd98b8767ed54b1531ed1666&camp=1789&creative=9325)/[3B+](https://www.amazon.com/ELEMENT-Element14-Raspberry-Pi-Motherboard/dp/B07P4LSDYV/?&_encoding=UTF8&tag=scidsg-20&linkCode=ur2&linkId=d76c1db453c42244fe465c9c56601303&camp=1789&creative=9325)
- **OS:** Raspberry Pi OS (64-bit)
- **Display** (Optional): [Waveshare 2.7" e-Paper display](https://www.amazon.com/2-7inch-HAT-Resolution-Electronic-Communicating/dp/B075FQKSZ9/?&_encoding=UTF8&tag=scidsg-20&linkCode=ur2&linkId=6963f1303b9d2b8ade8f92f37f2fda26&camp=1789&creative=9325)

Hush Line deploys to either an onion-only instance or Tor + public web. It's a web and email server and a Python app that encrypts a message with your public PGP key once a message gets submitted, then saves it, and finally emails the encrypted message to you. Your data never gets saved in an unencrypted state. And since all messages are sent to your email, you never have to log in to the device.

For install instructions [read the docs](https://github.com/scidsg/hushline/tree/main/docs), or [check out the full tutorial on Medium.](https://scidsg.medium.com/installing-and-configuring-hush-line-on-a-raspberry-pi-daefc3865020)

![hush-cover](https://github.com/scidsg/hush-line/assets/28545431/b776d0e0-73a0-4024-b67a-07c4188dd9af)

## References

1. https://www.sauteed-onions.org/
