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

# Enter and test SMTP credentials
test_smtp_credentials() {
    python3 << END
import smtplib

def test_smtp_credentials(smtp_server, smtp_port, email, password):
    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(email, password)
        server.quit()
        return True
    except smtplib.SMTPException as e:
        print(f"SMTP Error: {e}")
        return False

if test_smtp_credentials("$NOTIFY_SMTP_SERVER", $NOTIFY_SMTP_PORT, "$EMAIL", "$NOTIFY_PASSWORD"):
    exit(0)  # Exit with status 0 if credentials are correct
else:
    exit(1)  # Exit with status 1 if credentials are incorrect
END
}

while : ; do  # This creates an infinite loop, which will only be broken when the SMTP credentials are verified successfully
    whiptail --title "Email Setup" --msgbox "Let's set up email notifications. You'll receive an encrypted email when someone submits a new message.\n\nAvoid using your primary email address since your password is stored in plaintext.\n\nInstead, we recommend using a Gmail account with a one-time password." 16 64
    EMAIL=$(whiptail --inputbox "Enter your email:" 8 60 3>&1 1>&2 2>&3)
    NOTIFY_SMTP_SERVER=$(whiptail --inputbox "Enter the SMTP server address (e.g., smtp.gmail.com):" 8 60 3>&1 1>&2 2>&3)
    NOTIFY_PASSWORD=$(whiptail --passwordbox "Enter the password for the email address:" 8 60 3>&1 1>&2 2>&3)
    NOTIFY_SMTP_PORT=$(whiptail --inputbox "Enter the SMTP server port (e.g., 465):" 8 60 3>&1 1>&2 2>&3)

    if test_smtp_credentials; then
        break  # If credentials are correct, break the infinite loop
    else
        whiptail --title "SMTP Credential Error" --msgbox "SMTP credentials are invalid. Please check your SMTP server address, port, email, and password, and try again." 10 60
    fi
done  # End of the loop

# Create a directory for the environment file with restricted permissions
mkdir -p /etc/hushline
chmod 700 /etc/hushline

# Create an environment file with restricted permissions
cat << EOL > /etc/hushline/environment
EMAIL=$EMAIL
NOTIFY_SMTP_SERVER=$NOTIFY_SMTP_SERVER
NOTIFY_PASSWORD=$NOTIFY_PASSWORD
NOTIFY_SMTP_PORT=$NOTIFY_SMTP_PORT
EOL
chmod 600 /etc/hushline/environment

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

echo "
👍 Public PGP key received.
Continuing with installation process..."

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
cat >/etc/systemd/system/hushline.service <<EOL
[Unit]
Description=Hush Line Web App
After=network.target
[Service]
User=root
WorkingDirectory=$HOME/hushline
EnvironmentFile=-/etc/hushline/environment
ExecStart=$PWD/venv/bin/gunicorn --bind 127.0.0.1:5000 app:app
Restart=always
[Install]
WantedBy=multi-user.target
EOL

# Make config read-only
chmod 444 /etc/systemd/system/hushline.service

systemctl enable hushline.service
systemctl start hushline.service

# Check if the application is running and listening on the expected address and port
sleep 5
if ! netstat -tuln | grep -q '127.0.0.1:5000'; then
    echo "The application is not running as expected. Please check the application logs for more details."
    error_exit
fi

# Create Tor configuration file
mv $HOME/hushline/assets/config/torrc /etc/tor

# Restart Tor service
systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(cat /var/lib/tor/hidden_service/hostname)

# Configure Nginx
cat >/etc/nginx/sites-available/hushline.nginx <<EOL
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
mv $HOME/hushline/assets/nginx/nginx.conf /etc/nginx

ln -sf /etc/nginx/sites-available/hushline.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hushline.nginx /etc/nginx/sites-enabled/
(nginx -t && systemctl restart nginx) || error_exit

# System status indicator
display_status_indicator() {
    local status="$(systemctl is-active hushline.service)"
    if [ "$status" = "active" ]; then
        printf "\n\033[32m●\033[0m Hush Line is running\n$ONION_ADDRESS\n\n"
    else
        printf "\n\033[31m●\033[0m Hush Line is not running\n\n"
    fi
}

# Create Info Page
cat >$HOME/hushline/templates/info.html <<EOL
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="author" content="Science & Design, Inc.">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="A reasonably private and secure personal tip line.">
    <meta name="theme-color" content="#7D25C1">

    <title>Hush Line Info</title>

    <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='favicon/apple-touch-icon.png') }}">
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon/favicon-32x32.png') }}" sizes="32x32">
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon/favicon-16x16.png') }}" sizes="16x16">
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon/android-chrome-192x192.png') }}" sizes="192x192">
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon/android-chrome-512x512.png') }}" sizes="512x512">
    <link rel="icon" type="image/x-icon" href="{{ url_for('static', filename='favicon/favicon.ico') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body class="info">
    <header>
        <div class="wrapper">
            <h1><a href="/" target="_blank">🤫 Hush Line</a></h1>
            <a href="https://en.wikipedia.org/wiki/Special:Random" class="btn" rel="noopener noreferrer">Close App</a>
        </div>
    </header>
    <section>
        <div class="wrapper">
            <h2>👋<br>Welcome to Hush Line</h2>
            <p>Hush Line is an anonymous tip line. You should use it when you have information you think shows evidence of wrongdoing, including:</p>
            <ul>
                <li>a violation of law, rule, or regulation,</li>
                <li>gross mismanagement,</li>
                <li>a gross waste of funds,</li>
                <li>abuse of authority, or</li>
                <li>a substantial danger to public health or safety.</li>
            </ul>
            <p>To send a Hush Line message, first, <a href="https://www.torproject.org/download/" target="_blank">download Tor Browser</a>, then use it to visit: <pre>http://$ONION_ADDRESS</pre></p>
        </div>
    </section>
    <script src="{{ url_for('static', filename='jquery-min.js') }}"></script>
    <script src="{{ url_for('static', filename='main.js') }}"></script>
</body>
</html>
EOL

# Configure Unattended Upgrades
mv $HOME/hushline/assets/config/50unattended-upgrades /etc/apt/apt.conf.d
mv $HOME/hushline/assets/config/20auto-upgrades /etc/apt/apt.conf.d

systemctl restart unattended-upgrades

echo "Automatic updates have been installed and configured."

# Configure Fail2Ban

echo "Configuring fail2ban..."

systemctl start fail2ban
systemctl enable fail2ban
cp /etc/fail2ban/jail.{conf,local}

# Configure fail2ban
mv $HOME/hushline/assets/config/jail.local /etc/fail2ban

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
    message = "Hush Line has been successfully installed! In a moment, your device will reboot.\n\nYou can visit your tip line when you see \"Hush Line is running\" on your e-Paper display. If you can't immediately connect, don't panic; this is normal, as your device's information sometimes takes a few minutes to publish.\n\nYour Hush Line address is:\nhttp://$ONION_ADDRESS\n\nTo send a message, enter your address into Tor Browser. To find information about your Hush Line, including tips for when to use it, visit: http://$ONION_ADDRESS/info. If you still need to download Tor Browser, get it from https://torproject.org/download.\n\nHush Line is a free and open-source tool by Science & Design, Inc. Learn more about us at https://scidsg.org.\n\nIf you've found this resource useful, please consider making a donation at https://opencollective.com/scidsg."

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
    local status=\"\$(systemctl is-active hushline.service)\"
    if [ \"\$status\" = \"active\" ]; then
        printf \"\n\033[32m●\033[0m Hush Line is running\nhttp://$ONION_ADDRESS\n\n\"
    else
        printf \"\n\033[31m●\033[0m Hush Line is not running\n\n\"
    fi
}" >>/etc/bash.bashrc

echo "display_status_indicator" >>/etc/bash.bashrc
source /etc/bash.bashrc

systemctl restart hushline

rm -r $HOME/hushline/assets

send_email

# Disable the trap before exiting
trap - ERR

# Reboot the device
echo "Rebooting..."
sleep 5
reboot
