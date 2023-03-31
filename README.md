# Hush Line
Hush Line is a reasonably secure and anonymous tip line that you can set up on your own domain name.

![social](https://user-images.githubusercontent.com/28545431/229231707-c0103aae-b740-4325-bf25-47822681ae2f.png)

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

Hush Line uses SMTP to send email notifications. To get it working, find your: 

- Email Address
- SMTP Address
- Port Number
- Password

👉 We recommend using a Gmail account with a one-time password since we store passwords in plaintext.
Your messages are encrypted, so Google won't be able to read their contents.
