# Hush Line Installation

## Installing on Digital Ocean

1. Go to digitalocean.com and create a new account or log in to an existing one.
2. Create a new Droplet.
- OS: Debian 11/12 x64
- Droplet type: Basic
- CPU options: Regular
- Price: $4/mo
3. Open a Terminal, and log in to your new Droplet using SSH:
```
ssh root@<IP>
```
4. We'll install Hush Line as root:
```
sudo su
```
5. Next, it's recommended to update your system and remove unused software before running any new commands:
```
apt update && apt -y dist-upgrade && apt -y autoremove
```
6. To install Hush Line, simply execute the following command:
```
curl -sSL https://install.hushline.app | bash
```
- You can choose a Tor-only install, or Tor and a public domain. I'm choosing Tor-only.
7. You'll need an SMTP-compatible email service. I'm using Gmail in my example:
- Google account
- SMTP address: smtp.gmail.com
- One-time/App password
- Port: 465
8. Make sure your public PGP key is uploaded to a public keyserver. For example: https://keys.openpgp.org/search?q=demoo@scidsg.org. 
- You need the address of your key, not the search result. For the example above, I would enter https://keys.openpgp.org/vks/v1/by-fingerprint/7B437253F81116E1B1DBFF69D5F9B36A5DC2CAF0 into the appropriate prompt.
9. When the installation completes, you'll see your Hush Line address:
```
✅ Installation complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org.

● Hush Line is running
http://vfalkrrucjb7pztjskfumnqytpze5iimu4i2t2ygwv6ntylvylt2flad.onion
```

## Installing on Raspberry Pi
1. Download the official Raspberry Pi Imager: https://www.raspberrypi.com/software/
2. Install Raspberry Pi OS (64-bit) to a micro SD card.
3. Open a Terminal, and log in to your Pi using SSH:
```
ssh pi@<IP>
```
4. We'll install Hush Line as root:
```
sudo su
```
5. Next, it's recommended to update your system and remove unused software before running any new commands:
```
apt update && apt -y dist-upgrade && apt -y autoremove
```
6. To install Hush Line, simply execute the following command:
```
curl -sSL https://install.hushline.app | bash
```
- You can choose a Tor-only install, or Tor and a public domain. I'm choosing Tor-only.

7. You'll need an SMTP-compatible email service. I'm using Gmail in my example:
- Google account
- SMTP address: smtp.gmail.com
- One-time/App password
- Port: 465
8. Make sure your public PGP key is uploaded to a public keyserver. For example: https://keys.openpgp.org/search?q=demoo@scidsg.org. 
- You need the address of your key, not the search result. For the example above, I would enter https://keys.openpgp.org/vks/v1/by-fingerprint/7B437253F81116E1B1DBFF69D5F9B36A5DC2CAF0 into the appropriate prompt.
9. When the installation completes, you'll see your Hush Line address:
```
✅ Installation complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org.

● Hush Line is running
http://vfalkrrucjb7pztjskfumnqytpze5iimu4i2t2ygwv6ntylvylt2flad.onion
```
