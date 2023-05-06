# Hush Line Documentation

## Table of Contents

* Introduction
* Architecture Overview
* Installation
* Configuration
* Maintaining and Updating
* Troubleshooting
* Support and Contact

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

