#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

#Update and upgrade
apt update && apt -y dist-upgrade && apt -y autoremove

# Install required packages
apt-get -y install git python3 python3-venv python3-pip nginx tor libnginx-mod-http-geoip geoip-database unattended-upgrades gunicorn libssl-dev net-tools fail2ban ufw

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call the error_exit function
trap error_exit ERR

# Email Notification Setup
whiptail --title "Email Setup" --msgbox "Let's set up email notifications. You'll receive an encrypted email when someone submits a new message.\n\nAvoid using your primary email address since your password is stored in plaintext.\n\nInstead, we recommend using a Gmail account with a one-time password." 16 64
EMAIL=$(whiptail --inputbox "Enter your email:" 8 60 3>&1 1>&2 2>&3)
NOTIFY_SMTP_SERVER=$(whiptail --inputbox "Enter the SMTP server address (e.g., smtp.gmail.com):" 8 60 3>&1 1>&2 2>&3)
NOTIFY_PASSWORD=$(whiptail --passwordbox "Enter the password for the email address:" 8 60 3>&1 1>&2 2>&3)
NOTIFY_SMTP_PORT=$(whiptail --inputbox "Enter the SMTP server port (e.g., 465):" 8 60 3>&1 1>&2 2>&3)

# Instruct the user
echo "
  ___  ___ ___   ___ _   _ ___ _    ___ ___   _  _______   __
 | _ \/ __| _ \ | _ \ | | | _ ) |  |_ _/ __| | |/ / __\ \ / /
 |  _/ (_ |  _/ |  _/ |_| | _ \ |__ | | (__  | ' <| _| \ V / 
 |_|  \___|_|   |_|  \___/|___/____|___\___| |_|\_\___| |_|  

👇 Please paste your public PGP key and press Enter."

PGP_PUBLIC_KEY=""
while IFS= read -r LINE < /dev/tty; do
    PGP_PUBLIC_KEY+="$LINE"$'\n'
    [[ $LINE == "-----END PGP PUBLIC KEY BLOCK-----" ]] && break
done

export DOMAIN
export EMAIL
export NOTIFY_PASSWORD
export NOTIFY_SMTP_SERVER
export NOTIFY_SMTP_PORT

# Create a virtual environment and install dependencies
cd hushline
python3 -m venv venv
source venv/bin/activate
pip3 install setuptools-rust
pip3 install flask
pip3 install pgpy
pip3 install gunicorn
pip3 install cryptography
pip3 install -r requirements.txt

# Save the provided PGP key to a file
echo "$PGP_PUBLIC_KEY" > $PWD/public_key.asc

# Create a systemd service
cat >/etc/systemd/system/hush-line.service <<EOL
[Unit]
Description=Hush Line Web App
After=network.target
[Service]
User=root
WorkingDirectory=$HOME/hushline
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

# Make config read-only
chmod 444 /etc/systemd/system/hush-line.service

systemctl enable hush-line.service
systemctl start hush-line.service

# Check if the application is running and listening on the expected address and port
sleep 5
if ! netstat -tuln | grep -q '127.0.0.1:5000'; then
    echo "The application is not running as expected. Please check the application logs for more details."
    error_exit
fi

# Create Tor configuration file
mv $HOME/hushline/assets/torrc /etc/tor

# Restart Tor service
systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(cat /var/lib/tor/hidden_service/hostname)

# Configure Nginx
cat >/etc/nginx/sites-available/hush-line.nginx <<EOL
server {
    listen 80;
    server_name localhost;
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
    
        add_header Strict-Transport-Security "max-age=63072000; includeSubdomains";
        add_header X-Frame-Options DENY;
        add_header Onion-Location http://$ONION_ADDRESS\$request_uri;
        add_header X-Content-Type-Options nosniff;
        add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'none'";
        add_header Permissions-Policy "geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=()";
        add_header Referrer-Policy "no-referrer";
        add_header X-XSS-Protection "1; mode=block";
}
EOL

# Configure Nginx with privacy-preserving logging
mv $HOME/hushline/assets/nginx.conf /etc/nginx

ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
(nginx -t && systemctl restart nginx) || error_exit

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
mv $HOME/hushline/assets/50unattended-upgrades /etc/apt/apt.conf.d
mv $HOME/hushline/assets/20auto-upgrades /etc/apt/apt.conf.d

systemctl restart unattended-upgrades

echo "Automatic updates have been installed and configured."

# Configure Fail2Ban

echo "Configuring fail2ban..."

systemctl start fail2ban
systemctl enable fail2ban
cp /etc/fail2ban/jail.{conf,local}

# Configure fail2ban
mv $HOME/hushline/assets/jail.local /etc/fail2ban

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
    HUSHLINE_PATH="$HOME/hushline"
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
    subject = "🎉 Hush Line Installation Complete"
    message = "Hush Line has been successfully installed! In a moment, your device will reboot.\n\nYou can visit your tip line when you see \"Hush Line is running\" on your e-Paper display. If you can't immediately connect, don't panic; this is normal, as your device's information sometimes takes a few minutes to publish.\n\nYour Hush Line address is:\nhttp://$ONION_ADDRESS\n\nTo send a message, enter your address into Tor Browser. If you still need to download it, get it from https://torproject.org/download.\n\nHush Line is a free and open-source tool by Science & Design, Inc. Learn more about us at https://scidsg.org.\n\nIf you've found this resource useful, please consider making a donation at https://opencollective.com/scidsg."

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

rm -r $HOME/hushline/assets
rm $HOME/hushline/scripts/install*

send_email

# Disable the trap before exiting
trap - ERR

# Reboot the device
echo "Rebooting..."
sleep 5
reboot
