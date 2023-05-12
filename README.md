# Hush Line
Hush Line is a reasonably secure and anonymous tip line that you can set up on your own domain name.

![wiki-cover](https://user-images.githubusercontent.com/28545431/235570788-51e55fe0-8774-453d-a3bf-5517b6d27e60.png)

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

## Add a Display
When hosted on a Raspberry Pi, you can optionally add an e-ink display that makes it easy for people in your phycial location to discover and access your Hush Line. Teachers can place one on their desks in a classroom, a school can host one in the common area where students gather, or a manager can have one in a team's collaboration space. 

The current working models:
* [waveshare 2.13" E-Ink Display HAT](https://www.waveshare.com/product/raspberry-pi/displays/e-paper/2.13inch-e-paper-hat.htm)
* [waveshare 2.7" E-Ink Display HAT](https://www.waveshare.com/2.7inch-e-paper-hat.htm)

### Waveshare 2.13" E-Ink Display
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/waveshare-2_13in_eink-display.sh | bash
```
![IMG_4686](https://github.com/scidsg/hush-line/assets/28545431/4b91ff4b-53f0-4be8-b8ec-f5f94361fbd8)

### Waveshare 2.7" E-Ink Display
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/waveshare-2_7in-eink-display.sh | bash
```
![eink](https://user-images.githubusercontent.com/28545431/236740191-84184588-8bcb-4cc6-b41d-a9aa6e50c68b.png)

