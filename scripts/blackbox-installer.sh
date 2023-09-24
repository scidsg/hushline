#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

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
