#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

#Update and upgrade
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove

# Install required packages
sudo apt-get -y install git python3 python3-venv python3-pip nginx tor libnginx-mod-http-geoip geoip-database unattended-upgrades gunicorn libssl-dev net-tools fail2ban ufw

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

systemctl enable hush-line.service
systemctl start hush-line.service

# Check if the application is running and listening on the expected address and port
sleep 5
if ! netstat -tuln | grep -q '127.0.0.1:5000'; then
    echo "The application is not running as expected. Please check the application logs for more details."
    error_exit
fi

# Create Tor configuration file
sudo tee /etc/tor/torrc <<EOL
RunAsDaemon 1
HiddenServiceDir /var/lib/tor/hidden_service/
HiddenServicePort 80 127.0.0.1:5000
EOL

# Restart Tor service
sudo systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(sudo cat /var/lib/tor/hidden_service/hostname)

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
cat >/etc/nginx/nginx.conf <<EOL
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;
events {
        worker_connections 768;
        # multi_accept on;
}
http {
        ##
        # Basic Settings
        ##
        sendfile on;
        tcp_nopush on;
        types_hash_max_size 2048;
        # server_tokens off;
        # server_names_hash_bucket_size 64;
        # server_name_in_redirect off;
        include /etc/nginx/mime.types;
        default_type application/octet-stream;
        ##
        # SSL Settings
        ##
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3; # Dropping SSLv3, ref: POODLE
        ssl_prefer_server_ciphers on;
        ##
        # Logging Settings
        ##
        # access_log /var/log/nginx/access.log;
        error_log /var/log/nginx/error.log;
        ##
        # Gzip Settings
        ##
        gzip on;
        # gzip_vary on;
        # gzip_proxied any;
        # gzip_comp_level 6;
        # gzip_buffers 16 8k;
        # gzip_http_version 1.1;
        # gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
        ##
        # Virtual Host Configs
        ##
        include /etc/nginx/conf.d/*.conf;
        include /etc/nginx/sites-enabled/*;
        ##
        # Enable privacy preserving logging
        ##
        geoip_country /usr/share/GeoIP/GeoIP.dat;
        log_format privacy '0.0.0.0 - \$remote_user [\$time_local] "\$request" \$status \$body_bytes_sent "\$http_referer" "-" \$geoip_country_code';

        access_log /var/log/nginx/access.log privacy;
}

EOL

sudo ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

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

# Enable the "security" and "updates" repositories
sudo sed -i 's/\/\/\s\+"\${distro_id}:\${distro_codename}-security";/"\${distro_id}:\${distro_codename}-security";/g' /etc/apt/apt.conf.d/50unattended-upgrades
sudo sed -i 's/\/\/\s\+"\${distro_id}:\${distro_codename}-updates";/"\${distro_id}:\${distro_codename}-updates";/g' /etc/apt/apt.conf.d/50unattended-upgrades
sudo sed -i 's|//\s*Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";|Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";|' /etc/apt/apt.conf.d/50unattended-upgrades
sudo sed -i 's|//\s*Unattended-Upgrade::Remove-Unused-Dependencies "true";|Unattended-Upgrade::Remove-Unused-Dependencies "true";|' /etc/apt/apt.conf.d/50unattended-upgrades

sudo sh -c 'echo "APT::Periodic::Update-Package-Lists \"1\";" > /etc/apt/apt.conf.d/20auto-upgrades'
sudo sh -c 'echo "APT::Periodic::Unattended-Upgrade \"1\";" >> /etc/apt/apt.conf.d/20auto-upgrades'

# Configure unattended-upgrades
echo 'Unattended-Upgrade::Automatic-Reboot "true";' | sudo tee -a /etc/apt/apt.conf.d/50unattended-upgrades
echo 'Unattended-Upgrade::Automatic-Reboot-Time "02:00";' | sudo tee -a /etc/apt/apt.conf.d/50unattended-upgrades

sudo systemctl restart unattended-upgrades

echo "Automatic updates have been installed and configured."

# Configure Fail2Ban

echo "Configuring fail2ban..."

sudo systemctl start fail2ban
sudo systemctl enable fail2ban
sudo cp /etc/fail2ban/jail.{conf,local}

cat >/etc/fail2ban/jail.local <<EOL
[DEFAULT]
bantime  = 10m
findtime = 10m
maxretry = 5

[sshd]
enabled = true

# 404 Errors
[nginx-http-auth]
enabled  = true
filter   = nginx-http-auth
port     = http,https
logpath  = /var/log/nginx/error.log
maxretry = 5

# Rate Limiting
[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
port     = http,https
logpath  = /var/log/nginx/error.log
maxretry = 5

# 403 Errors
[nginx-botsearch]
enabled  = true
filter   = nginx-botsearch
port     = http,https
logpath  = /var/log/nginx/access.log
maxretry = 10

# Bad Bots and Crawlers
[nginx-badbots]
enabled  = true
filter   = nginx-badbots
port     = http,https
logpath  = /var/log/nginx/access.log
maxretry = 2
EOL

sudo systemctl restart fail2ban

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
if [[ $(uname -n) == *"raspberrypi"* ]]; then
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
warnings.filterwarnings("ignore", category=DeprecationWarning)

def send_notification_email(smtp_server, smtp_port, email, password):
    subject = "🎉 Hush Line Installation Complete"
    message = "Hush Line has been successfully installed!\n\nYour Hush Line address is $ONION_ADDRESS."

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

sudo systemctl restart hush-line

send_email

# Disable the trap before exiting
trap - ERR
