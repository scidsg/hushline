# Hush Line
Hush Line is a self-hosted, lightweight private tip line and anonymous suggestion box. Journalists and newsrooms can use Hush Line to give the public an easy way to submit anonymous tips. Educators and schools can use Hush Line to provide students with a safe way to send a message to an adult they trust. And workplaces can use it by Boards of Directors and senior executives hosting a Hush Line instance and providing employees a trustworthy way to securely report ethical or legal issues without revealing their identities.

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

## Hush Line Go
Take Hush Line Go with you when you're on the move to make sharing your address easy. With the e-paper display, once the text is written, it will remain indefinitely without requiring power.

Supported display:
[Adafruit 2.13" Monochrome E-Ink Bonnet](https://www.adafruit.com/product/4687)

```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/companion-device.sh | bash
```

![IMG_4686](https://github.com/scidsg/hush-line/assets/28545431/4b91ff4b-53f0-4be8-b8ec-f5f94361fbd8)

This device displays the encoded URL for your main Hush Line app, instructions, and the owner's info. Notably, when the device is plugged in, it acts as a listener for your tip line, pinging its address every minute and reporting when it was last seen. So if your server's availability is impacted, you'll know immediately.

And since this device only points to your main Hush Line app and contains no sensitive data, you don't have to worry if you lose it.

## Add a Display to Your Pi Server
When hosted on a Raspberry Pi, you can optionally add an e-ink display that makes it easy for people in your phycial location to discover and access your Hush Line. Teachers can place one on their desks in a classroom, a school can host one in the common area where students gather, or a manager can have one in a team's collaboration space. 

```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/waveshare-2_7in-eink-display.sh | bash
```
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/waveshare-2_13in_eink-display.sh | bash
```

Supported models:
* [waveshare 2.7" E-Paper Display HAT](https://www.waveshare.com/2.7inch-e-paper-hat.htm)
* [waveshare 2.13" E-Paper Display HAT](https://www.waveshare.com/product/raspberry-pi/displays/e-paper/2.13inch-e-paper-hat.htm)

![IMG_4793 1](https://github.com/scidsg/hush-line/assets/28545431/8a85b9d5-9196-4783-a5ed-91bc34dd29a8)
![213](https://github.com/scidsg/hush-line/assets/28545431/8336b178-d0e1-43c3-b1dc-87c5756dc582)
