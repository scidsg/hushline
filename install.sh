#!/bin/bash

# Add your ASCII art here
cat << "EOF"
  _    _           _       _      _            
 | |  | |         | |     | |    (_)           
 | |__| |_   _ ___| |__   | |     _ _ __   ___ 
 |  __  | | | / __| '_ \  | |    | | '_ \ / _ \
 | |  | | |_| \__ \ | | | | |____| | | | |  __/
 |_|  |_|\__,_|___/_| |_| |______|_|_| |_|\___|
                                               
🤫 Your Private Suggestion Box 
https://hushline.app

EOF

sleep 3

#Update and upgrade
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove

# Install required packages
sudo apt-get -y install git python3 python3-venv python3-pip certbot python3-certbot-nginx nginx whiptail tor libnginx-mod-http-geoip geoip-database

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

clone_and_install_dependencies() {
# Clone the repository
git clone https://github.com/scidsg/hush-line.git

# Create a virtual environment and install dependencies
cd hush-line
python3 -m venv venv
source venv/bin/activate
pip3 install flask
pip3 install pgpy
pip3 install -r requirements.txt
}

enable_hushline() {
systemctl enable hush-line.service
systemctl start hush-line.service
}

configure_nginx() {
# Configure Nginx
cat > /etc/nginx/nginx.conf << EOL
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

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit
}

configure_onion_service() {
# Create Tor configuration file
sudo tee /etc/tor/torrc << EOL
RunAsDaemon 1
HiddenServiceDir /var/lib/tor/hidden_service/
HiddenServicePort 80 127.0.0.1:5000
EOL

check_application() {
    sleep 5
if ! netstat -tuln | grep -q '127.0.0.1:5000'; then
    echo "The application is not running as expected. Please check the application logs for more details."
    error_exit
fi
}

# Restart Tor service
sudo systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(sudo cat /var/lib/tor/hidden_service/hostname)

# Enable the Tor hidden service
sudo ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
}

prompt_email() {
# Prompt user for email
EMAIL=$(whiptail --inputbox "Enter your email:" 8 60 3>&1 1>&2 2>&3)

# Prompt user for email notification settings
NOTIFY_SMTP_SERVER=$(whiptail --inputbox "Enter the SMTP server address (e.g., smtp.gmail.com):" 8 60 3>&1 1>&2 2>&3)
NOTIFY_PASSWORD=$(whiptail --passwordbox "Enter the password for the email address:" 8 60 3>&1 1>&2 2>&3)
NOTIFY_SMTP_PORT=$(whiptail --inputbox "Enter the SMTP server port (e.g., 465):" 8 60 3>&1 1>&2 2>&3)
}

# Trap any errors and call the error_exit function
trap error_exit ERR

# Prompt user to choose installation type
INSTALL_TYPE=$(whiptail --title "Welcome to 🤫 Hush Line!" --menu "Welcome to Hush Line, your private tip line and suggestion box.\n\nYou can install Hush Line as a Tor-only implementation, or make it available on both Tor and a public website.\n\nChoose your preferred installation type:" 16 60 3 \
    "1" "🧅 Tor-only " \
    "2" "🧅 Tor + 🌎 Public web" 3>&1 1>&2 2>&3)

if [ "$INSTALL_TYPE" != "2" ]; then

# Welcome Prompt
whiptail --title "🤫 Hush Line Installation" --msgbox "Hush Line provides a simple way to receive secure messages from sources, colleagues, clients, or patients.\n\nAfter installation, you'll have a private tip line hosted on your own server, secured with PGP, and available on a .onion address so anyone can message you, even from locations where censorship is prevalent." 16 64

# Welcome Prompt
whiptail --title "Email Setup" --msgbox "Let's set up email notifications. You'll receive an encrypted email when someone submits a new message.\n\nAvoid using your primary email address since your password is stored in plaintext.\n\nInstead, we recommend using a burner address or a Gmail account with a one-time password." 16 64

# Prompt user for email notification settings
prompt_email

export EMAIL
export NOTIFY_PASSWORD
export NOTIFY_SMTP_SERVER
export NOTIFY_SMTP_PORT

# Clone the repository and create a virtual environment and install dependencies
clone_and_install_dependencies

# Create a systemd service
cat > /etc/systemd/system/hush-line.service << EOL
[Unit]
Description=Tip-Line Web App
After=network.target
[Service]
User=root
WorkingDirectory=$PWD
Environment="DOMAIN=localhost"
Environment="EMAIL=$EMAIL"
Environment="NOTIFY_PASSWORD=$NOTIFY_PASSWORD"
Environment="NOTIFY_SMTP_SERVER=$NOTIFY_SMTP_SERVER"
Environment="NOTIFY_SMTP_PORT=$NOTIFY_SMTP_PORT"
ExecStart=$PWD/venv/bin/python3 $PWD/app.py
Restart=always
[Install]
WantedBy=multi-user.target
EOL

enable_hushline

# Check if the application is running and listening on the expected address and port
check_application

# Create Tor configuration file
configure_onion_service

# Configure Nginx
cat > /etc/nginx/sites-available/hush-line.nginx << EOL
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

# Configure Nginx
configure_nginx

echo "
✅ Installation complete!
                                               
http://$ONION_ADDRESS
Hush Line is a product by Science & Design. Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org.
"
fi

if [ "$INSTALL_TYPE" != "1" ]; then

# Welcome Prompt
whiptail --title "🤫 Hush Line Installation" --msgbox "Hush Line provides a simple way to receive secure messages from sources, colleagues, clients, or patients.\n\nAfter installation, you'll have a private tip line hosted on your own server, secured with PGP, HTTPS, and available on a .onion address so anyone can message you, even from locations where censorship is prevalent.\n\nBefore you begin, ensure your website's DNS settings point to this server." 16 64

# Prompt user for domain name
DOMAIN=$(whiptail --inputbox "Enter your domain name:" 8 60 3>&1 1>&2 2>&3)

# Welcome Prompt
whiptail --title "Email Setup" --msgbox "Now we'll set up email notifications. You'll receive an encrypted email when someone submits a new message.\n\nAvoid using your primary email address since your password is stored in plaintext.\n\nInstead, we recommend using a burner address or a Gmail account with a one-time password." 16 64

# Prompt user for email notification settings
prompt_email

# Check for valid domain name format
until [[ $DOMAIN =~ ^[a-zA-Z0-9][a-zA-Z0-9\.-]*\.[a-zA-Z]{2,}$ ]]; do
    DOMAIN=$(whiptail --inputbox "Invalid domain name format. Please enter a valid domain name:" 8 60 3>&1 1>&2 2>&3)
done
export DOMAIN
export EMAIL
export NOTIFY_PASSWORD
export NOTIFY_SMTP_SERVER
export NOTIFY_SMTP_PORT

# Debug: Print the value of the DOMAIN variable
echo "Domain: ${DOMAIN}"

# Clone the repository and create a virtual environment and install dependencies
clone_and_install_dependencies

# Create a systemd service
cat > /etc/systemd/system/hush-line.service << EOL
[Unit]
Description=Tip-Line Web App
After=network.target
[Service]
User=root
WorkingDirectory=$PWD
Environment="DOMAIN=$DOMAIN"
Environment="EMAIL=$EMAIL"
Environment="NOTIFY_PASSWORD=$NOTIFY_PASSWORD"
Environment="NOTIFY_SMTP_SERVER=$NOTIFY_SMTP_SERVER"
Environment="NOTIFY_SMTP_PORT=$NOTIFY_SMTP_PORT"
ExecStart=$PWD/venv/bin/python3 $PWD/app.py
Restart=always
[Install]
WantedBy=multi-user.target
EOL

enable_hushline

# Check if the application is running and listening on the expected address and port
check_application

# Create Tor configuration file
configure_onion_service

# Configure Nginx
cat > /etc/nginx/sites-available/hush-line.nginx << EOL
server {
    listen 80;
    server_name ${DOMAIN};
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
        add_header Permissions-Policy 'geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=()';
        add_header Referrer-Policy "no-referrer";
        add_header X-XSS-Protection "1; mode=block";
}
EOL

# Configure Nginx
configure_nginx

# Obtain SSL certificate
certbot --nginx --agree-tos --non-interactive --email ${EMAIL} --agree-tos -d $DOMAIN

# Set up cron job to renew SSL certificate
(crontab -l 2>/dev/null; echo "30 2 * * 1 /usr/bin/certbot renew --quiet") | crontab -

echo "
✅ Installation complete!
                                               
https://$DOMAIN
http://$ONION_ADDRESS
Hush Line is a product by Science & Design. Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org.
"
fi

# Disable the trap before exiting
