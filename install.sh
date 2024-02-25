#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Welcome message and ASCII art
cat <<"EOF"
 _   _           _       _     _            
| | | |_   _ ___| |__   | |   (_)_ __   ___ 
| |_| | | | / __| '_ \  | |   | | '_ \ / _ \
|  _  | |_| \__ \ | | | | |___| | | | |  __/
|_| |_|\__,_|___/_| |_| |_____|_|_| |_|\___|

🤫 Hush Line is the first free and open-source anonymous-tip-line-as-a-service for organizations and individuals.
https://hushline.app

A free tool by Science & Design - https://scidsg.org

EOF
sleep 3

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call the error_exit function
trap error_exit ERR

# Update packages and install whiptail
export DEBIAN_FRONTEND=noninteractive
apt update && apt -y dist-upgrade 
apt install whiptail -y

# Collect variables using whiptail
DB_NAME=$(whiptail --inputbox "Enter the database name" 8 39 "hushlinedb" --title "Database Name" 3>&1 1>&2 2>&3)
DB_USER=$(whiptail --inputbox "Enter the database username" 8 39 "hushlineuser" --title "Database Username" 3>&1 1>&2 2>&3)
DB_PASS=$(whiptail --passwordbox "Enter the database password" 8 39 "dbpassword" --title "Database Password" 3>&1 1>&2 2>&3)
STRIPE_SECRET_KEY=$(whiptail --inputbox "Enter the Stripe secret key" 8 39 "sk_test_51OhDeALcBPqjxU07nk5zZ0eWvTRDgBc0u9bLjmRhXmzTczwPHq28yBwF3I9NugqnT4N5QZFr1Keb906DzEOFHXHY00ugAXDHrA" --title "Stripe Secret Key" 3>&1 1>&2 2>&3)
STRIPE_WH_SECRET=$(whiptail --inputbox "Enter the Stripe Webhook Signing Secret" 8 39 --title "Stripe Webhook Secret" 3>&1 1>&2 2>&3)

# Install Python, pip, Git, Nginx, and MariaDB
sudo apt install python3 python3-pip git nginx default-mysql-server python3-venv gnupg tor certbot python3-certbot-nginx libnginx-mod-http-geoip ufw fail2ban -y

############################
# Server, Nginx, HTTPS setup
############################

DOMAIN=$(whiptail --inputbox "Enter your domain name:" 8 60 "beta.hushline.app" 3>&1 1>&2 2>&3)
EMAIL=$(whiptail --inputbox "Enter your email:" 8 60 "hushline@scidsg.org" 3>&1 1>&2 2>&3)
GIT=$(whiptail --inputbox "Enter your git repo's URL:" 8 60 "https://github.com/scidsg/hushline" 3>&1 1>&2 2>&3)

# Check for valid domain name format
until [[ $DOMAIN =~ ^[a-zA-Z0-9][a-zA-Z0-9\.-]*\.[a-zA-Z]{2,}$ ]]; do
    DOMAIN=$(whiptail --inputbox "Invalid domain name format. Please enter a valid domain name:" 8 60 3>&1 1>&2 2>&3)
done
export DOMAIN
export EMAIL
export GIT

# Debug: Print the value of the DOMAIN variable
echo "Domain: $DOMAIN"

# Create Tor configuration file
tee /etc/tor/torrc << EOL
RunAsDaemon 1
HiddenServiceDir /var/lib/tor/$DOMAIN/
HiddenServicePort 80 unix:/var/www/html/$DOMAIN/hushline-hosted.sock
EOL

# Restart Tor service
systemctl restart tor.service
sleep 10

# Get the Onion address
ONION_ADDRESS=$(cat /var/lib/tor/$DOMAIN/hostname)
SAUTEED_ONION_ADDRESS=$(echo $ONION_ADDRESS | tr -d '.')

# Configure Nginx
cat > /etc/nginx/sites-available/$DOMAIN.nginx << EOL
server {
        root /var/www/html/$DOMAIN;
        server_name $DOMAIN;
        location / {
            proxy_pass http://unix:/var/www/html/$DOMAIN/hushline-hosted.sock;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_connect_timeout 300s;
            proxy_send_timeout 300s;
            proxy_read_timeout 300s;
        }

        location = /.well-known/security.txt {
            alias /var/www/html/$DOMAIN/.well-known/security.txt;
        }
                
        add_header Strict-Transport-Security "max-age=63072000; includeSubdomains";
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header Onion-Location http://$ONION_ADDRESS\$request_uri;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://js.stripe.com https://unpkg.com; img-src 'self' data: https:; style-src 'self'; frame-ancestors 'none'; connect-src 'self' https://api.stripe.com; child-src https://js.stripe.com; frame-src https://js.stripe.com;";
        add_header Permissions-Policy "geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=()";
        add_header Referrer-Policy "no-referrer";
        add_header X-XSS-Protection "1; mode=block";
}
server {
        server_name $ONION_ADDRESS;
        access_log /var/log/nginx/hs-my-website.log;
        index index.html;
        root /var/www/html/$DOMAIN;
                
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://js.stripe.com https://unpkg.com; img-src 'self' data: https:; style-src 'self'; frame-ancestors 'none'; connect-src 'self' https://api.stripe.com; child-src https://js.stripe.com; frame-src https://js.stripe.com;";
        add_header Permissions-Policy "geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=()";
        add_header Referrer-Policy "no-referrer";
        add_header X-XSS-Protection "1; mode=block";
}
server {
        listen 80;
        server_name $DOMAIN; # YOUR URLS
        return 301 https://$DOMAIN\$request_uri;
}
server {
    listen 80;
    server_name $SAUTEED_ONION_ADDRESS.$DOMAIN;

    location / {
        proxy_pass http://unix:/var/www/html/$DOMAIN/hushline-hosted.sock;
    }
}
EOL

# Configure Nginx with privacy-preserving logging
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
        server_names_hash_bucket_size 128;
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
        log_format privacy '0.0.0.0 - \$remote_user "\$request" \$status \$body_bytes_sent "\$http_referer"';

        access_log /var/log/nginx/access.log privacy;
}
EOL

ln -sf /etc/nginx/sites-available/$DOMAIN.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/$DOMAIN.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit

cd /var/www/html
git clone $GIT
REPO_NAME=$(basename $GIT .git)
mv $REPO_NAME $DOMAIN

SERVER_IP=$(curl -s ifconfig.me)
WIDTH=$(tput cols)
whiptail --msgbox --title "Instructions" "\nPlease ensure that your DNS records are correctly set up before proceeding:\n\nAdd an A record with the name: @ and content: $SERVER_IP\n* Add a CNAME record with the name $SAUTEED_ONION_ADDRESS.$DOMAIN and content: $DOMAIN\n* Add a CAA record with the name: @ and content: 0 issue \"letsencrypt.org\"\n" 14 $WIDTH
# Request the certificates
echo "⏲️  Waiting 30 seconds for DNS to update..."
sleep 30
certbot --nginx -d $DOMAIN,$SAUTEED_ONION_ADDRESS.$DOMAIN --agree-tos --non-interactive --no-eff-email --email ${EMAIL}

echo "Configuring automatic renewing certificates..."
# Set up cron job to renew SSL certificate
(crontab -l 2>/dev/null; echo "30 2 * * 1 /usr/bin/certbot renew --quiet") | crontab -
echo "✅ Automatic HTTPS certificates configured."

# Enable IPv6 in Nginx configuration
NGINX_CONF="/etc/nginx/sites-available/$DOMAIN.nginx"
sed -i '/listen 80;/a \    listen [::]:80;' $NGINX_CONF
sed -i '/listen 443 ssl;/a \    listen [::]:443 ssl;' $NGINX_CONF
echo "✅ IPv6 configuration appended to Nginx configuration file."

# Append OCSP Stapling configuration for SSL
sed -i "/listen \[::\]:443 ssl;/a \    ssl_stapling on;\n    ssl_stapling_verify on;\n    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;\n    resolver 9.9.9.9 1.1.1.1 valid=300s;\n    resolver_timeout 5s;\n    ssl_session_cache shared:SSL:10m;" $NGINX_CONF
echo "✅ OCSP Stapling, SSL Session, and Resolver Timeout added."

# Test the Nginx configuration and reload if successful
nginx -t && systemctl reload nginx || echo "Error: Nginx configuration test failed, please check the configuration."

####################################
####################################

cd $DOMAIN

# Download hello@scidsg.org key referenced in the security.txt file
wget https://keys.openpgp.org/vks/v1/by-fingerprint/1B539E29F407E9E8896035DF8F4E83FB1B785F8E > public.asc

mkdir -p .well-known

# Configure Nginx with privacy-preserving logging
cat > /var/www/html/$DOMAIN/.well-known/security.txt << EOL
Contact: mailto:security@scidsg.org
Expires: 2025-01-01T00:00:00Z
Encryption: https://$DOMAIN/public.asc
Acknowledgments: https://github.com/scidsg/hushline/blob/main/ACKNOWLEDGMENTS.md
Policy: https://github.com/scidsg/hushline/blob/main/SECURITY.md
Canonical: https://$DOMAIN/.well-known/security.txt
EOL

# Temporarily disable the error trap
trap - ERR

# Ask the user if paid features should be enabled by default
PAID_FEATURES_ENABLED=$(whiptail --title "Enable Paid Features" --yesno "Do you want to enable paid features by default for all users?" 8 78 3>&1 1>&2 2>&3)

exitstatus=$?
if [ $exitstatus = 0 ]; then
    # User selected Yes, enable paid features by default
    echo "Enabling paid features by default..."
    sed -i 's/has_paid = db.Column(db.Boolean, default=False)/has_paid = db.Column(db.Boolean, default=True)/' /var/www/html/$DOMAIN/app.py
else
    # User selected No, keep the default setting
    echo "Keeping paid features disabled by default..."
fi

# Re-enable the error trap
trap error_exit ERR

mkdir -p ~/.gnupg
chmod 700 ~/.gnupg

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Flask and other dependencies
pip3 install -r requirements.txt

SECRET_KEY=$(python3 -c 'import os; print(os.urandom(64).hex())')
ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

# Store in .env file
echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" > .env
echo "DB_NAME=$DB_NAME" >> .env  
echo "DB_USER=$DB_USER" >> .env
echo "DB_PASS=$DB_PASS" >> .env
echo "SECRET_KEY=$SECRET_KEY" >> .env
echo "STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY" >> .env
echo "STRIPE_WH_SECRET=$STRIPE_WH_SECRET" >> .env

# Start MariaDB
systemctl start mariadb

# Secure MariaDB Installation
mysql_secure_installation

# Create an override file for MariaDB to restart on failure
echo "Creating MariaDB service override..."
mkdir -p /etc/systemd/system/mariadb.service.d
echo -e "[Service]\nRestart=on-failure\nRestartSec=5s" | tee /etc/systemd/system/mariadb.service.d/override.conf

# Reload the systemd daemon and restart MariaDB to apply changes
systemctl daemon-reload
systemctl restart mariadb

sudo mkdir -p /etc/mariadb/ssl

sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/mariadb/ssl/
sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /etc/mariadb/ssl/

sudo chown mysql:mysql /etc/mariadb/ssl/fullchain.pem /etc/mariadb/ssl/privkey.pem
sudo chmod 400 /etc/mariadb/ssl/fullchain.pem /etc/mariadb/ssl/privkey.pem

# MariaDB configuration file path
MY_CNF="/etc/mysql/my.cnf"

# Append SSL configuration to the MariaDB configuration file
echo "ssl_cert=/etc/mariadb/ssl/fullchain.pem" | sudo tee -a $MY_CNF > /dev/null
echo "ssl_key=/etc/mariadb/ssl/privkey.pem" | sudo tee -a $MY_CNF > /dev/null

# Restart MariaDB to apply the new configuration
sudo systemctl restart mariadb

echo "✅ SSL configuration has been added to MariaDB."

# Check if the database exists, create if not
if ! mysql -sse "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = '$DB_NAME')" | grep -q 1; then
    mysql -e "CREATE DATABASE $DB_NAME;"
fi

# Check if the user exists and create it if it doesn't
if ! mysql -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '$DB_USER' AND host = 'localhost')" | grep -q 1; then
    mysql -e "CREATE USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
    mysql -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';"
    mysql -e "FLUSH PRIVILEGES;"
fi

# Verify Database Connection and Initialize DB
echo "Verifying database connection and initializing database..."
if ! python init_db.py; then
    echo "Database initialization failed. Please check your settings."
    exit 1
else
    echo "✅ Database initialized successfully."
fi

# Define the working directory
WORKING_DIR=$(pwd)

# Create a systemd service file for the Flask app
SERVICE_FILE=/etc/systemd/system/hushline-hosted.service
cat <<EOF | tee $SERVICE_FILE
[Unit]
Description=Gunicorn instance to serve the Hushline Flask app
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=$WORKING_DIR
ExecStart=$WORKING_DIR/venv/bin/gunicorn --workers 2 --bind unix:$WORKING_DIR/hushline-hosted.sock -m 007 --timeout 120 wsgi:app

[Install]
WantedBy=multi-user.target
EOF

# Create an override file for the Hushline service to restart on failure
echo "Creating Hushline service override..."
mkdir -p /etc/systemd/system/hushline-hosted.service.d
echo -e "[Service]\nRestart=on-failure\nRestartSec=5s" | tee /etc/systemd/system/hushline-hosted.service.d/override.conf

# Start and enable the Flask app service
systemctl daemon-reload
systemctl start hushline-hosted
systemctl enable hushline-hosted
systemctl restart hushline-hosted

# Restart Nginx to apply changes
systemctl restart nginx

# Start and enable Nginx
systemctl enable nginx

# Enable the "security" and "updates" repositories
echo "Configuring unattended-upgrades..."
cp assets/50unattended-upgrades /etc/apt/apt.conf.d
cp assets/20auto-upgrades /etc/apt/apt.conf.d

systemctl restart unattended-upgrades

echo "✅ Automatic updates have been installed and configured."

# Configure Fail2Ban

echo "Configuring fail2ban..."

systemctl start fail2ban
systemctl enable fail2ban
cp /etc/fail2ban/jail.{conf,local}

# Configure fail2ban
cp assets/jail.local /etc/fail2ban

systemctl restart fail2ban

echo "✅ Fail2Ban configuration complete."

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

# Enable UFW non-interactively
echo "y" | ufw enable

echo "✅ UFW configuration complete."

# Remove unused packages
apt -y autoremove

# Generate Codes
chmod +x generate_codes.sh
./generate_codes.sh

# Update Tor permissions
# Create a systemd override directory for the Tor service
mkdir -p /etc/systemd/system/tor@default.service.d

# Create an override file with an ExecStartPost command and restart on failure for the Tor service
cat <<EOT > /etc/systemd/system/tor@default.service.d/override.conf
[Service]
Restart=on-failure
RestartSec=5s
ExecStartPost=/bin/sh -c 'until [ -S /var/www/html/$DOMAIN/hushline-hosted.sock ]; do sleep 1; done; chown debian-tor:www-data /var/www/html/$DOMAIN/hushline-hosted.sock'
EOT

# Reload the systemd daemon to apply the override
systemctl daemon-reload


echo "
✅ Hush Line installation complete! Access your site at these addresses:
                                               
https://$DOMAIN
https://$SAUTEED_ONION_ADDRESS.$DOMAIN;
http://$ONION_ADDRESS
"

echo "⏲️ Rebooting in 10 seconds..."
sleep 10
reboot
