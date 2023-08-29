# Installation Guide

[Option 1: Digital Ocean](#option-1-digital-ocean)

[Option 2: Raspberry Pi](#option-2-raspberry-pi)

## Option 1: Digital Ocean

### Step 1: Create a Digital Ocean account

1. Go to [digitalocean.com](digitalocean.com) and create a new account or log in to an existing one.
2. [Create a new Droplet](https://docs.digitalocean.com/products/droplets/how-to/create/).
- **OS:** Debian 11/12 x64
- **Droplet type:** Basic
- **CPU options:** Regular
- **Price:** $4/mo

### Step 2: Log in to and update your VPS

1. Open a Terminal, and log in to your new Droplet using SSH:
```
ssh root@<IP>
```
2. Next, it's recommended to update your system and remove unused software before running any new commands:
```
apt update && apt -y dist-upgrade && apt -y autoremove
```
### Step 3: Install Hush Line

1. To install Hush Line, simply execute the following command. This guide uses a Tor-only install.
```
curl -sSL https://install.hushline.app | bash
```

### Step 4: SMTP Notifications

1. To receive email notifications you'll need an SMTP-compatible email service. We're using Gmail in our example and need the following information:
- Gmail address
- SMTP address: smtp.gmail.com
- [App password](https://support.google.com/accounts/answer/185833?hl=en)
- Port: 465
- If our Gmail address is myburneremail@gmail.com, email notifications would be delivered to that Gmail account.
  - Remember that you can choose to forward messages to any address in your Gmail settings.

### Step 5: Create and add your PGP key

#### MacOS

1. Download and install [GPG Suite](https://gpgtools.org/).
2. Open GPG Keychain.
3. Click "New" at the top of the window.
4. Create a key for the email address of your tip line. _You do not have to use your notification email address_. Science & Design uses "tips@scidsg.org" for our purposes. It's critical to enter an email address that you own which can receive a confirmation email.
5. After creating your key, choose to upload it to a public keyserver. You'll need to confirm your email address before it finishes uploading. 
6. On the appropriate prompt during install, enter the address of your uploaded key. For example, for our key seen at https://keys.openpgp.org/search?q=demo@scidsg.org, we would enter https://keys.openpgp.org/vks/v1/by-fingerprint/7B437253F81116E1B1DBFF69D5F9B36A5DC2CAF0 into the appropriate prompt.

### Step 6: Access Hush Line

1. When the installation completes, you'll see your Hush Line address:
```
✅ Installation complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org.

● Hush Line is running
http://vfalkrrucjb7pztjskfumnqytpze5iimu4i2t2ygwv6ntylvylt2flad.onion
```
2. To access your tip line, download [Tor Browser](https://torproject.org/download) and enter the onion address above.

## Option 2: Raspberry Pi

### Requirements
- **Hardware:** [Raspberry Pi 4](https://www.amazon.com/Raspberry-Model-2019-Quad-Bluetooth/dp/B07TC2BK1X/?&_encoding=UTF8&tag=scidsg-20&linkCode=ur2&linkId=ee402e41cd98b8767ed54b1531ed1666&camp=1789&creative=9325)/[3B+](https://www.amazon.com/ELEMENT-Element14-Raspberry-Pi-Motherboard/dp/B07P4LSDYV/?&_encoding=UTF8&tag=scidsg-20&linkCode=ur2&linkId=d76c1db453c42244fe465c9c56601303&camp=1789&creative=9325)
- **OS:** Raspberry Pi OS (64-bit)
- **Display** (Optional): [Waveshare 2.7" e-Paper display](https://www.amazon.com/2-7inch-HAT-Resolution-Electronic-Communicating/dp/B075FQKSZ9/?&_encoding=UTF8&tag=scidsg-20&linkCode=ur2&linkId=6963f1303b9d2b8ade8f92f37f2fda26&camp=1789&creative=9325)
- (👆 Affiliate links)

### Step 1: Install Raspberry Pi OS
1. Download the official Raspberry Pi Imager: https://www.raspberrypi.com/software/
2. Install Raspberry Pi OS (64-bit) to a micro SD card.

### Step 2: Log in to your Pi
1. Open a Terminal, and log in to your Pi using SSH:
```
ssh pi@<IP>
```
2. We'll install Hush Line as root:
```
sudo su
```

### Step 3: Install Hush Line

1. To install Hush Line, simply execute the following command. This guide uses a Tor-only install.
```
curl -sSL https://install.hushline.app | bash
```

### Step 4: SMTP Notifications

1. To receive email notifications you'll need an SMTP-compatible email service. We're using Gmail in our example and need the following information:
- Gmail address
- SMTP address: smtp.gmail.com
- [App password](https://support.google.com/accounts/answer/185833?hl=en)
- Port: 465
- If our Gmail address is myburneremail@gmail.com, email notifications would be delivered to that Gmail account.
  - Remember that you can choose to forward messages to any address in your Gmail settings.

### Step 5: Create and add your PGP key

#### MacOS

1. Download and install [GPG Suite](https://gpgtools.org/).
2. Open GPG Keychain.
3. Click "New" at the top of the window.
4. Create a key for the email address of your tip line. _You do not have to use your notification email address_. Science & Design uses "tips@scidsg.org" for our purposes. It's critical to enter an email address that you own which can receive a confirmation email.
5. After creating your key, choose to upload it to a public keyserver. You'll need to confirm your email address before it finishes uploading. 
6. On the appropriate prompt during install, enter the address of your uploaded key. For example, for our key seen at https://keys.openpgp.org/search?q=demo@scidsg.org, we would enter https://keys.openpgp.org/vks/v1/by-fingerprint/7B437253F81116E1B1DBFF69D5F9B36A5DC2CAF0 into the appropriate prompt.


### Step 6: Access Hush Line

1. When the installation completes, you'll see your Hush Line address:
```
✅ Installation complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org.

● Hush Line is running
http://vfalkrrucjb7pztjskfumnqytpze5iimu4i2t2ygwv6ntylvylt2flad.onion
```
2. To access your tip line, download [Tor Browser](https://torproject.org/download) and enter the onion address above.
