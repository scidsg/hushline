# Hush Line Documentation

## Table of Contents

* [Introduction](#introduction)
* [Architecture Overview](#architecture-overview)
* [Installation](#installation)
* [Configuration](#configuration)
* [Maintaining and Updating](#maintaining-and-updating)
* [E-Ink Displays](#e-ink-displays)
* [Troubleshooting](#troubleshooting)
* [Support and Contact](#support-and-contact)

## Introduction

Hush Line is a secure and anonymous tip line and suggestion box application. It allows users to receive messages securely from sources, colleagues, clients, or patients. The application is designed to be self-hosted, with PGP encryption, HTTPS, and a .onion address for Tor access, ensuring maximum privacy and security for both the sender and receiver.

This documentation provides an overview of the application's architecture, installation instructions, configuration details, maintenance procedures, troubleshooting tips, and support information.

## Architecture Overview

Hush Line is built using the following components:

* Python with Flask as the web application framework.
* PGP encryption using the PGPy library.
* Nginx as a reverse proxy server, handling HTTPS connections and forwarding requests to the Flask application.
* Certbot for obtaining SSL certificates from Let's Encrypt.
* Tor for onion service access, allowing the application to be accessed via a .onion address.
* Systemd service for managing the Hush Line application.

## Installation

Save the provided installation script as a shell script (e.g., install_hush_line.sh).

Run the script in the terminal with the following command:

### Tor + Public Web
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/install.sh | bash
```

### Tor-Only
```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/install-tor-only.sh | bash
```

The script will guide you through the installation process, prompting you for the necessary information such as your domain name, email, and email server settings.

Before installation, ensure your domain's DNS settings are correctly pointing to your server's IP address.

Verify that Hush Line is running by accessing the application using the provided addresses.

## Configuration

During the installation process, the script configures the following components:

* Systemd service for managing the Hush Line application.
* Tor hidden service for .onion access.
* Nginx reverse proxy server for SSL termination and forwarding requests to the Flask application.
* Certbot for SSL certificate management.
* Automatic updates via unattended-upgrades.

## Maintaining and Updating

**Regular updates:** The unattended-upgrades package is configured to automatically update your server, including security updates. No manual intervention is needed.

**SSL certificate renewal:** The installation script sets up a cron job to automatically renew the SSL certificates using Certbot.

## E-Ink Displays

In this section, we'll discuss how to set up an e-ink display for your Hush Line project. The e-ink display will show the status of your Hush Line instance, onion address, and QR code for easy access to the service. The script provided will install necessary packages and configure the Raspberry Pi for proper communication with the e-ink display.

![hush-line-display](https://user-images.githubusercontent.com/28545431/236598264-728eb43a-d23c-4dac-a13d-7487e3fe88ea.png)

### Setup

To set up the e-ink display, exectue the following command in your terminal:

```
curl -sSL https://raw.githubusercontent.com/scidsg/tools/main/hushline-eink-rpi-display.sh | bash
```

The script will install the required packages, configure the SPI interface, set up the Waveshare e-Paper library, and create necessary Python scripts for managing the e-ink display. It will also download a splash screen image and enable a service to clear the display before shutdown.

Once the setup script has finished running, your Raspberry Pi will automatically reboot for the changes to take effect.

### E-Ink Display Functionality

The e-ink display will show:

* The status of your Hush Line instance (running or not running)
* Onion address of your Hush Line instance
* QR code to access your Hush Line instance
* PGP public key information (name, email, key ID, and expiration date)

The script will refresh the e-ink display every minute to provide up-to-date information.

### E-Ink Display Management

The provided script includes two Python scripts for managing the e-ink display:

**display_status.py:** Displays the status, onion address, QR code, and PGP public key information on the e-ink display.

**clear_display.py:** Clears the e-ink display.

These scripts are automatically run on boot and before shutdown, respectively. You can also run them manually if needed.

## Troubleshooting

If Hush Line is not running, check the status using the following command:

```
systemctl status hush-line.service
```

If there are any issues with Nginx, verify the configuration using the following command:

```
sudo nginx -t
```

Check the logs for Hush Line, Nginx, and Tor for any error messages or clues:

**Hush Line:** /var/log/syslog

**Nginx:** /var/log/nginx/error.log

**Tor:** /var/log/tor/log

## Support and Contact

If you have any questions, feedback, or need assistance, please contact us at:

**Website:** https://scidsg.org

**Email:** support@scidsg.org

