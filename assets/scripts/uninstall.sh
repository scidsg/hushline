#!/bin/bash

# This script should be run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root."
    exit 1
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

# Stop the Hush Line service and disable it
systemctl stop hushline.service
systemctl disable hushline.service
rm /etc/systemd/system/hushline.service
systemctl daemon-reload

# Remove the Hush Line application directory
rm -rf /home/hush/hushline

# Remove created Nginx configuration and reload Nginx
rm /etc/nginx/sites-available/hushline.nginx
rm /etc/nginx/sites-available/hushline-setup.nginx
rm /etc/nginx/sites-enabled/hushline.nginx
rm /etc/nginx/sites-enabled/hushline-setup.nginx
nginx -t && systemctl reload nginx

# Uninstall packages installed by the script
apt-get remove --purge -y git python3-pip nginx tor gunicorn libssl-dev jq fail2ban ufw redis-server
apt-get autoremove -y

# Remove mkcert and its generated certificates
rm /usr/local/bin/mkcert
rm -rf /home/hush/.local/share/mkcert
rm /etc/nginx/hushline.local.pem
rm /etc/nginx/hushline.local-key.pem

# Re-enable SSH (if previously disabled)
ufw allow proto tcp from any to any port 22
apt-get install -y openssh-server openssh-client

# Disable UFW
ufw disable

# Re-enable USB
sed -i '/dtoverlay=disable-usb/d' /boot/config.txt

# Re-enable Bluetooth
rfkill unblock bluetooth

echo "Hush Line has been uninstalled. System reboot required to complete USB and Bluetooth reactivation."

# Optional: Prompt for reboot
read -p "Reboot now? (y/N): " reboot_choice
if [[ $reboot_choice =~ ^[Yy]$ ]]; then
    shutdown -r now
fi
