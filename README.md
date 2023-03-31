# Hush Line
Hush Line is a reasonably secure and anonymous tip line that you can set up on your own domain name.

![hush-cover](https://user-images.githubusercontent.com/28545431/228141667-89fbaeb8-8282-4f86-a575-bdb29f9ffe31.png)

## Easy Install

```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/install.sh | bash
```

![demo](https://user-images.githubusercontent.com/28545431/228354332-010d5124-286a-44fe-9b65-1bdaf3165ad1.gif)

**Requirements**

- Debian-based Linux distribution (e.g. Ubuntu)
- git
- Python 3.6 or higher
- virtualenv
- pip
- certbot
- nginx
- whiptail

## Installation

Update and upgrade your system:

```
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove
```

## Email Notifications

Hush Line sends an email notification with the encrypted messages that sources submit. Passwords are stored in plaintext, so our recommendation is to use a Gmail account with a one-time password. Since the messages are encrypted, Google can't see the contents. 

