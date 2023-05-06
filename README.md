# Hush Line
Hush Line is a reasonably secure and anonymous tip line that you can set up on your own domain name.

![wiki-cover](https://user-images.githubusercontent.com/28545431/235570788-51e55fe0-8774-453d-a3bf-5517b6d27e60.png)

## Easy Install
👉 We recommend using a Gmail account with a one-time password since we store passwords in plaintext.
Your messages are encrypted, so Google won't be able to read their contents.

### Tor + Public Web
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/install.sh | bash
```

### Tor-Only
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/install-tor-only.sh | bash
```

## Add a Display
When hosted on a Raspberry Pi, you can optionally add an e-ink display that makes it easy for people in your phycial location to discover and access your Hush Line. Teachers can place one on their desks in a classroom, a school can host one in the common area where students gather, or a manager can have one in a team's collaboration space. 

![hush-line-display](https://user-images.githubusercontent.com/28545431/236576931-b44b01a0-727b-4b47-8f6a-cc7c22c2b924.png)

The current working models:
* [waveshare 2.7inch E-Ink Display HAT](https://www.waveshare.com/2.7inch-e-paper-hat.htm)

After Hush Line installation, simply run:
```
curl -sSL https://raw.githubusercontent.com/scidsg/tools/main/hushline-eink-rpi-display.sh | bash
```
