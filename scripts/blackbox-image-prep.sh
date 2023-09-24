#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

git clone https://github.com/waveshare/e-Paper.git
git clone https://github.com/scidsg/hushline.git

mv e-paper/ hushline/

# Clear display before shutdown
cat >/etc/systemd/system/blackbox-installer.service <<EOL
[Unit]
Description=Blackbox Installer
After=multi-user.target

[Service]
ExecStart=/home/hush/hushline/blackbox-installer.sh
Type=oneshot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL

sudo systemctl enable blackbox-installer.service
