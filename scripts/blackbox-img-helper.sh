#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Enable SPI interface
raspi-config

# Update system
apt update && apt -y dist-upgrade && apt -y autoremove

git clone https://github.com/scidsg/hushline.git
chmod +x /home/hush/hushline/scripts/qr-installer-beta.sh

# Create a new script to display status on the e-ink display
cat >/etc/systemd/system/blackbox-installer.service <<EOL
[Unit]
Description=Blackbox Installation Helper
After=multi-user.target

[Service]
ExecStart=/home/hush/hushline/scripts/qr-installer-beta.sh
Type=oneshot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL

sudo systemctl enable blackbox-installer.service

sudo apt-get -y install git python3 python3-venv python3-pip nginx tor libnginx-mod-http-geoip geoip-database unattended-upgrades gunicorn libssl-dev net-tools jq

# Install Waveshare e-Paper library
pip3 install flask setuptools-rust pgpy gunicorn cryptography segno requests
pip3 install qrcode[pil]
pip3 install requests python-gnupg

# Install other Python packages
pip3 install RPi.GPIO spidev