#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Update and upgrade
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove

# Install required packages
sudo apt-get -y install git python3 python3-venv python3-pip nginx tor whiptail libnginx-mod-http-geoip geoip-database unattended-upgrades gunicorn libssl-dev net-tools jq

# Install Waveshare e-Paper library
pip3 install /home/hush/hushline/e-Paper/RaspberryPi_JetsonNano/python/
pip3 install qrcode[pil]
pip3 install requests python-gnupg

# Install other Python packages
pip3 install RPi.GPIO spidev

pip3 install flask setuptools-rust pgpy gunicorn cryptography segno requests
pip3 install -r requirements.txt

# Clone the repositories

git clone https://github.com/waveshare/e-Paper.git
git clone https://github.com/scidsg/hushline.git

mv e-paper/ hushline/

# Clear display before shutdown
cat >/etc/systemd/system/blackbox-installer.service <<EOL
[Unit]
Description=Blackbox Installer
After=multi-user.target

[Service]
ExecStart=/home/hush/hushline/scripts/blackbox-beta-installer.sh
Type=oneshot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL

sudo systemctl enable blackbox-installer.service
