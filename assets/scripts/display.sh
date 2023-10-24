#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Install required packages for e-ink display
apt update
apt-get -y dist-upgrade
apt-get install -y python3-pip

# Install Waveshare e-Paper library
pip3 install /home/hush/hushline/e-Paper/RaspberryPi_JetsonNano/python/
pip3 install qrcode[pil]
pip3 install requests python-gnupg

# Install other Python packages
pip3 install RPi.GPIO spidev
apt-get -y autoremove

# Create a new script to display status on the e-ink display
mv /home/hush/hushline/assets/python/display_status.py /home/hush/hushline
mv /home/hush/hushline/assets/python/clear_display.py /home/hush/hushline

# Clear display before shutdown
mv /home/hush/hushline/assets/service/clear-display.service /etc/systemd/system
mv /home/hush/hushline/assets/service/display-status.service /etc/systemd/system
systemctl daemon-reload
systemctl enable clear-display.service
systemctl enable display-status.service
systemctl start display-status.service

# Download splash screen image
cd /home/hush/hushline
wget https://raw.githubusercontent.com/scidsg/hushline-assets/main/images/splash.png

echo "✅ E-ink display configuration complete. Rebooting Hush Line..."
sleep 3

systemctl disable hushline-installer.service
echo "✅ Web installer disabled..."

echo "Rebooting in 3 seconds. Press CTRL + C to cancel."
sleep 3
reboot