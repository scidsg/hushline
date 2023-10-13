#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call error_exit function
trap error_exit ERR

# Update and upgrade
apt update && apt -y dist-upgrade && apt -y autoremove

# Install required packages
apt-get -y install git python3 python3-venv python3-pip nginx tor whiptail libnginx-mod-http-geoip geoip-database unattended-upgrades gunicorn libssl-dev net-tools jq fail2ban ufw

# Install mkcert and its dependencies
echo "Installing mkcert and its dependencies..."
apt install -y libnss3-tools
wget https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-v1.4.4-linux-arm64
sleep 10
chmod +x mkcert-v1.4.4-linux-arm64
mv mkcert-v1.4.4-linux-arm64 /usr/local/bin/mkcert
export CAROOT="/home/hush/.local/share/mkcert"
mkdir -p "$CAROOT"  # Ensure the directory exists
mkcert -install

# Create a certificate for hushline.local
echo "Creating certificate for hushline.local..."
mkcert hushline.local

# Move and link the certificates to Nginx's directory (optional, modify as needed)
mv hushline.local.pem /etc/nginx/
mv hushline.local-key.pem /etc/nginx/
echo "Certificate and key for hushline.local have been created and moved to /etc/nginx/."

# Create a virtual environment and install dependencies
cd /home/hush/hushline
git restore --source=HEAD --staged --worktree -- .
git reset HEAD -- .
git clean -fd .
git config pull.rebase false
git pull

python3 -m venv venv
source venv/bin/activate
pip3 install flask setuptools-rust pgpy gunicorn cryptography segno requests
pip3 install -r requirements.txt

# Install Waveshare e-Paper library
if [ ! -d "e-Paper" ]; then
    git clone https://github.com/waveshare/e-Paper.git
else
    echo "Directory e-Paper already exists. Skipping clone."
fi
pip3 install ./e-Paper/RaspberryPi_JetsonNano/python/
pip3 install qrcode[pil]
pip3 install requests python-gnupg

# Install other Python packages
pip3 install RPi.GPIO spidev
apt-get -y autoremove

# Enable SPI interface
if ! grep -q "dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" | tee -a /boot/config.txt
    echo "SPI interface enabled."
else
    echo "SPI interface is already enabled."
fi

# Create a new script to capture information
mv /home/hush/blackbox-bullseye/python/blackbox-setup.py /home/hush/hushline

# Configure Nginx
mv /home/hush/blackbox-bullseye/nginx/hushline-setup.nginx /etc/nginx/sites-available

ln -sf /etc/nginx/sites-available/hushline-setup.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hushline-setup.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit

# Create a new script to display status on the e-ink display
mv /home/hush/blackbox-bullseye/python/qr-setup.py /home/hush/hushline
mv /home/hush/blackbox-bullseye/templates/setup.html /home/hush/hushline/templates

nohup ./venv/bin/python3 qr-setup.py --host=0.0.0.0 &

# Launch Flask app for setup
nohup ./venv/bin/python3 blackbox-setup.py --host=0.0.0.0 &

sleep 5

# Display the QR code from the file
cat /tmp/qr_code.txt

echo "The Flask app for setup is running. Please complete the setup by navigating to https://hushline.local/setup."

# Wait for user to complete setup form
while [ ! -f "/tmp/setup_config.json" ]; do
    sleep 5
done

# Read the configuration
EMAIL=$(jq -r '.email' /tmp/setup_config.json)
NOTIFY_SMTP_SERVER=$(jq -r '.smtp_server' /tmp/setup_config.json)
NOTIFY_PASSWORD=$(jq -r '.password' /tmp/setup_config.json)
NOTIFY_SMTP_PORT=$(jq -r '.smtp_port' /tmp/setup_config.json)

# Kill the Flask setup process and delete the install script
pkill -f blackbox-setup.py
rm /home/hush/hushline/blackbox-setup.py
rm /etc/nginx/sites-available/hushline-setup.nginx
rm /etc/nginx/sites-enabled/hushline-setup.nginx

# Create a systemd service
cat >/etc/systemd/system/hush-line.service <<EOL
[Unit]
Description=Hush Line Web App
After=network.target
[Service]
User=root
WorkingDirectory=$PWD
Environment="DOMAIN=localhost"
Environment="EMAIL=$EMAIL"
Environment="NOTIFY_PASSWORD=$NOTIFY_PASSWORD"
Environment="NOTIFY_SMTP_SERVER=$NOTIFY_SMTP_SERVER"
Environment="NOTIFY_SMTP_PORT=$NOTIFY_SMTP_PORT"
ExecStart=$PWD/venv/bin/gunicorn --bind 127.0.0.1:5000 app:app
Restart=always
[Install]
WantedBy=multi-user.target
EOL

# Make service file read-only and remove temp file
chmod 444 /etc/systemd/system/hush-line.service
rm /tmp/setup_config.json

systemctl daemon-reload
systemctl enable hush-line.service
systemctl start hush-line.service

# Check if the application is running and listening on the expected address and port
sleep 5
if ! netstat -tuln | grep -q '127.0.0.1:5000'; then
    echo "The application is not running as expected. Please check the application logs for more details."
    error_exit
fi

# Create Tor configuration file
mv /home/hush/blackbox-bullseye/torrc /etc/tor

# Restart Tor service
systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(cat /var/lib/tor/hidden_service/hostname)

# Configure Nginx
mv /home/hush/blackbox-bullseye/nginx/hush-line.nginx /etc/nginx/sites-available
mv /home/hush/blackbox-bullseye/nginx/nginx.conf /etc/nginx

ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit

# System status indicator
display_status_indicator() {
    local status="$(systemctl is-active hush-line.service)"
    if [ "$status" = "active" ]; then
        printf "\n\033[32m●\033[0m Hush Line is running\n$ONION_ADDRESS\n\n"
    else
        printf "\n\033[31m●\033[0m Hush Line is not running\n\n"
    fi
}

# Configure Unattended Upgrades
mv /home/hush/blackbox-bullseye/config/50unattended-upgrades /etc/apt/apt.conf.d
mv /home/hush/blackbox-bullseye/config/20auto-upgrades /etc/apt/apt.conf.d

systemctl restart unattended-upgrades

echo "Automatic updates have been installed and configured."

# Configure Fail2Ban

echo "Configuring fail2ban..."

systemctl start fail2ban
systemctl enable fail2ban
cp /etc/fail2ban/jail.{conf,local}

mv /home/hush/blackbox-bullseye/config/jail.local /etc/fail2ban

systemctl restart fail2ban

# Configure UFW (Uncomplicated Firewall)

echo "Configuring UFW..."

# Default rules
ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp
ufw allow 443/tcp

# Allow SSH (modify as per your requirements)
ufw allow ssh
ufw limit ssh/tcp

# Logging
ufw logging on

# Enable UFW non-interactively
echo "y" | ufw enable

echo "UFW configuration complete."

HUSHLINE_PATH=""

# Detect the environment (Raspberry Pi or VPS) based on some characteristic
if [[ $(uname -n) == *"hushline"* ]]; then
    HUSHLINE_PATH="/home/hush/hushline"
else
    HUSHLINE_PATH="/root/hushline" # Adjusted to /root/hushline for the root user on VPS
fi

send_email() {
    python3 << END
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pgpy
import warnings
from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

def send_notification_email(smtp_server, smtp_port, email, password):
    subject = "🎉 Blackbox Installation Complete"
    message = "Blackbox has been successfully installed! In a moment, your device will reboot.\n\nYou can visit your tip line when you see \"Blackbox is running\" on your e-Paper display. If you can't immediately connect, don't panic; this is normal, as your device's information sometimes takes a few minutes to publish.\n\nYour Hush Line address is:\nhttp://$ONION_ADDRESS\n\nTo send a message, enter your address into Tor Browser. If you still need to download it, get it from https://torproject.org/download.\n\nHush Line is a free and open-source tool by Science & Design, Inc. Learn more about us at https://scidsg.org.\n\nIf you've found this resource useful, please consider making a donation at https://opencollective.com/scidsg."

    # Load the public key from its path
    key_path = os.path.expanduser('$HUSHLINE_PATH/public_key.asc')  # Use os to expand the path
    with open(key_path, 'r') as key_file:
        key_data = key_file.read()
        PUBLIC_KEY, _ = pgpy.PGPKey.from_blob(key_data)

    # Encrypt the message
    encrypted_message = str(PUBLIC_KEY.encrypt(pgpy.PGPMessage.new(message)))

    # Construct the email
    msg = MIMEMultipart()
    msg['From'] = email
    msg['To'] = email
    msg['Subject'] = subject
    msg.attach(MIMEText(encrypted_message, 'plain'))

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(email, password)
        server.sendmail(email, [email], msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

send_notification_email("$NOTIFY_SMTP_SERVER", $NOTIFY_SMTP_PORT, "$EMAIL", "$NOTIFY_PASSWORD")
END
}

echo "
✅ Installation complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org."

# Display system status on login
echo "display_status_indicator() {
    local status=\"\$(systemctl is-active hush-line.service)\"
    if [ \"\$status\" = \"active\" ]; then
        printf \"\n\033[32m●\033[0m Hush Line is running\nhttp://$ONION_ADDRESS\n\n\"
    else
        printf \"\n\033[31m●\033[0m Hush Line is not running\n\n\"
    fi
}" >>/etc/bash.bashrc

echo "display_status_indicator" >>/etc/bash.bashrc
source /etc/bash.bashrc

systemctl restart hush-line

send_email

deactivate

# Disable the trap before exiting
trap - ERR

curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/scidsg/blackbox-bullseye/main/display.sh | bash