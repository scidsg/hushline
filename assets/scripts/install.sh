#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Check to see if internet connection is available before proceeding
check_internet_connection() {
    while true; do
        # Ping Google's public DNS for a quick check.
        if ping -c 1 hushline.app &>/dev/null; then
            echo "👍 Internet connection detected!"
            break
        else
            echo "⏲️ Waiting for an internet connection..."
            # Wait for 5 seconds before checking again
            sleep 5
        fi
    done
}

check_internet_connection

# Update and upgrade non-interactively
export DEBIAN_FRONTEND=noninteractive
apt update && apt -y dist-upgrade -o Dpkg::Options::="--force-confnew" && apt -y autoremove

# Install required packages
apt -y install sudo wget curl git python3 python3-venv python3-pip nginx tor whiptail unattended-upgrades gunicorn libssl-dev net-tools jq fail2ban ufw


# Function to kill process on a given port
kill_process_on_port() {
    local port="$1"
    local pids
    pids=$(lsof -t -i :"$port")
    
    if [ -z "$pids" ]; then
        echo "No process found on port $port."
    else
        echo "Killing processes on port $port: $pids"
        echo "$pids" | xargs kill -9
    fi
}

# Stop anything using necessary ports
kill_process_on_port 5000
kill_process_on_port 5001

# Clone the repository in the user's home directory
cd /home/hush
if [[ ! -d hushline ]]; then
    # If the hushline directory does not exist, clone the repository
    git clone https://github.com/scidsg/hushline.git
else
    # If the hushline directory exists, clean the working directory and pull the latest changes
    echo "👍 The directory 'hushline' already exists, updating repository..."
    cd hushline
    git restore --source=HEAD --staged --worktree -- .
    git reset HEAD -- .
    git clean -fd .
    git config pull.rebase false
    git pull
    cd /home/hush # return to HOME for next steps
fi

# "reset" the terminal window before running first whiptail prompt
reset

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

cd /home/hush/hushline
python3 -m venv venv
source venv/bin/activate
pip3 install flask setuptools-rust pgpy gunicorn cryptography segno requests
pip3 install -r requirements.txt

# Generate a strong secret key and store it securely
FLASK_SECRET_KEY=$(python3 -c 'import os; print(os.urandom(24).hex())')
echo "FLASK_SECRET_KEY=${FLASK_SECRET_KEY}" > /home/hush/hushline/.env
chmod 600 /home/hush/hushline/.env

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

# Create a new script to capture information
cp /home/hush/hushline/assets/python/web_setup.py /home/hush/hushline

# Configure Nginx
cp /home/hush/hushline/assets/nginx/hushline-setup.nginx /etc/nginx/sites-available

ln -sf /etc/nginx/sites-available/hushline-setup.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx


if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hushline-setup.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit

# Move script to display status on the e-ink display
cp /home/hush/hushline/assets/python/qr_setup_link.py /home/hush/hushline

nohup ./venv/bin/python3 qr_setup_link.py --host=0.0.0.0 &

# Launch Flask app for setup
nohup ./venv/bin/python3 web_setup.py --host=0.0.0.0 &

sleep 5

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
pkill -f web_setup.py
rm /home/hush/hushline/web_setup.py
rm /etc/nginx/sites-available/hushline-setup.nginx
rm /etc/nginx/sites-enabled/hushline-setup.nginx

# Configure the systemd service for Flask app
cat >/etc/systemd/system/hushline.service <<EOL
[Unit]
Description=Hush Line Web App
After=network.target

[Service]
User=root
WorkingDirectory=$PWD
EnvironmentFile=/home/hush/hushline/.env
Environment="DOMAIN=localhost"
Environment="EMAIL=$EMAIL"
Environment="NOTIFY_PASSWORD=$NOTIFY_PASSWORD"
Environment="NOTIFY_SMTP_SERVER=$NOTIFY_SMTP_SERVER"
Environment="NOTIFY_SMTP_PORT=$NOTIFY_SMTP_PORT"
ExecStart=/home/hush/hushline/venv/bin/gunicorn "app:create_app()" --workers 3 --bind 127.0.0.1:5000
Restart=always

[Install]
WantedBy=multi-user.target

EOL

# Make service file read-only and remove temp file
chmod 444 /etc/systemd/system/hushline.service
rm /tmp/setup_config.json

systemctl daemon-reload
systemctl enable hushline.service
systemctl start hushline.service

# Check if the application is running and listening on the expected address and port
sleep 5
if ! netstat -tuln | grep -q '127.0.0.1:5000'; then
    echo "The application is not running as expected. Please check the application logs for more details."
    error_exit
fi

# Create Tor configuration file
mv /home/hush/hushline/assets/config/torrc /etc/tor

# Restart Tor service
systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(cat /var/lib/tor/hidden_service/hostname)

# Configure Nginx
cp /home/hush/hushline/assets/nginx/hushline.nginx /etc/nginx/sites-available
cp /home/hush/hushline/assets/nginx/nginx.conf /etc/nginx

ln -sf /etc/nginx/sites-available/hushline.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hushline.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit

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
cat >/home/hush/hushline/templates/info.html <<EOL
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
            <h1>Hush Line<br><span class="subhead">Personal Server</span></h1>
            <a href="https://en.wikipedia.org/wiki/Special:Random" class="btn" rel="noopener noreferrer">Close App</a>
        </div>
    </header>
    <section>
        <div>
            <h2>👋<br>Welcome to Hush Line</h2>
            <p>Hush Line is an anonymous tip line. You should use it when you have information you think shows evidence of wrongdoing, including:</p>
            <ul>
                <li>a violation of law, rule, or regulation,</li>
                <li>gross mismanagement,</li>
                <li>a gross waste of funds,</li>
                <li>abuse of authority, or</li>
                <li>a substantial danger to public health or safety.</li>
            </ul>
            <p>To send a Hush Line message, visit: <pre>http://$ONION_ADDRESS</pre></p>
            <p>🆘 If you're in immediate danger, stop what you're doing and contact your local authorities.</p>
            <p><a href="https://hushline.app" target="_blank" aria-label="Learn about Hush Line" rel="noopener noreferrer">Hush Line</a> is a free and open-source product by <a href="https://scidsg.org" aria-label="Learn about Science & Design, Inc." target="_blank" rel="noopener noreferrer">Science & Design, Inc.</a> If you've found this tool helpful, <a href="https://opencollective.com/scidsg" target="_blank" aria-label="Donate to support our work" rel="noopener noreferrer">please consider supporting our work!</p>
        </div>
    </section>
    <script src="{{ url_for('static', filename='jquery-min.js') }}"></script>
    <script src="{{ url_for('static', filename='main.js') }}"></script>
</body>
</html>
EOL

# Configure Unattended Upgrades
cp /home/hush/hushline/assets/config/50unattended-upgrades /etc/apt/apt.conf.d
cp /home/hush/hushline/assets/config/20auto-upgrades /etc/apt/apt.conf.d

systemctl restart unattended-upgrades

echo "Automatic updates have been installed and configured."

# Configure Fail2Ban

echo "Configuring fail2ban..."

systemctl start fail2ban
systemctl enable fail2ban
cp /etc/fail2ban/jail.{conf,local}

cp /home/hush/hushline/assets/config/jail.local /etc/fail2ban

systemctl restart fail2ban

HUSHLINE_PATH="/home/hush/hushline"

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

cp /home/hush/hushline/assets/python/send_email.py /home/hush/hushline
nohup ./venv/bin/python3 send_email.py "$NOTIFY_SMTP_SERVER" "$NOTIFY_SMTP_PORT" "$EMAIL" "$NOTIFY_PASSWORD" "$HUSHLINE_PATH" "$ONION_ADDRESS"

deactivate

# Disable the trap before exiting
trap - ERR

cd /home/hush/hushline/assets/scripts
chmod +x display.sh
./display.sh
