#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Welcome message and ASCII art
cat <<"EOF"
  _    _           _       _      _            
 | |  | |         | |     | |    (_)           
 | |__| |_   _ ___| |__   | |     _ _ __   ___ 
 |  __  | | | / __| '_ \  | |    | | '_ \ / _ \
 | |  | | |_| \__ \ | | | | |____| | | | |  __/
 |_|  |_|\__,_|___/_| |_| |______|_|_| |_|\___|
 __                            __                
|__)  _  _  _  _   _   _  |   (_   _  _     _  _ 
|    (- |  _) (_) | ) (_| |   __) (- |  \/ (- |  
                                                                                                
🤫 A self-hosted, anonymous tip line. Learn more at hushline.app
EOF
sleep 3

whiptail --title "Hush Line Home Server" --msgbox "The Hush Line Home Server is meant to be deployed to a Raspberry Pi, either headless, or with a Waveshare e-Paper 2.7\" display. If you want to install Hush Line to a VPS, use the install script in the repository's main branch. " 16 64

# Enable SPI interface
raspi-config nonint do_spi 0

# Update system
apt update && apt -y dist-upgrade && apt -y autoremove && apt install -y git

git clone https://github.com/scidsg/hushline.git
cd hushline
git switch personal-server
chmod +x /home/hush/hushline/assets/scripts/install.sh

# Move script to display status on the e-ink display to proper location
cp /home/hush/hushline/assets/service/hushline-installer.service /etc/systemd/system

systemctl daemon-reload
systemctl enable hushline-installer.service
apt-get -y install redis-server git python3 python3-venv python3-pip nginx tor unattended-upgrades gunicorn libssl-dev net-tools jq ufw rfkill

# Install Waveshare e-Paper library
pip3 install flask setuptools-rust pgpy gunicorn cryptography segno requests
pip3 install qrcode[pil]
pip3 install requests python-gnupg

# Install other Python packages
pip3 install RPi.GPIO spidev

# Configure UFW (Uncomplicated Firewall)
echo "Configuring UFW..."

# Default rules
ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp
ufw allow 443/tcp

# Disable and remove SSH
ufw deny proto tcp from any to any port 22
echo "🔒 SSH disabled..."

echo "Removing SSH server and client..."
apt-get -y purge openssh-server openssh-client
echo "🔒 SSH server and client removed."

# Enable UFW non-interactively
echo "y" | ufw enable
echo "🔒 Firewall enabled."

# Block Bluetooth
echo "Disabling Bluetooth..."
rfkill block bluetooth
echo "🔒 Bluetooth disabled."

# Disable USB
echo "Disabling USB access..."
echo "dtoverlay=disable-usb" | tee -a /boot/config.txt
echo "🔒 USB access disabled."
sleep 3

# Shutdown the system
echo "Shutting down in 3 seconds..."
sleep 3
shutdown -h now
