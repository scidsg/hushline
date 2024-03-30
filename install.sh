#!/bin/bash

####################################################################################################
# VARIABLES
####################################################################################################

DOMAIN="test.ourdemo.app"
EMAIL="hushline@scidsg.org"
GIT="https://github.com/scidsg/hushline"
HUSHLINE_USER="hushlineuser"
HUSHLINE_GROUP="www-data"
SERVICE_FILE="/etc/systemd/system/hushline-hosted.service"
MY_CNF="/etc/mysql/my.cnf"
TORRC_PATH="/etc/tor/torrc"
DOMAIN_CONFIG="HiddenServiceDir /var/lib/tor/$DOMAIN/"
NGINX_SITE_PATH="/etc/nginx/sites-available/hushline.nginx"
NGINX_CONF_PATH="/etc/nginx/nginx.conf"


####################################################################################################
# BEGIN SCRIPT
####################################################################################################

set -euo pipefail

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


####################################################################################################
# INSTALLATION STUFF
####################################################################################################

# Update packages and install whiptail
export DEBIAN_FRONTEND=noninteractive
apt update && apt -y dist-upgrade 

# Install Python, pip, Git, Nginx, and MariaDB
apt install -y \
    python3 \
    python3-pip \
    git \
    nginx \
    default-mysql-server \
    python3-venv \
    tor \
    libnginx-mod-http-geoip \
    redis \
    redis-server

cd /var/www/html
if [ ! -d hushline ]; then
    git clone $GIT
fi
cd hushline

if ! command -v rustc &> /dev/null; then
    echo "Rust is not installed. Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
else
    echo "Rust is already installed."
fi

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Debian only have 1.3.2, and we need 1.6.0 or higher
curl -sSL https://install.python-poetry.org | python3 -
export PATH="/root/.local/bin:$PATH"
echo 'export PATH="/root/.local/bin:$PATH"' >> ~/.bashrc
poetry lock
poetry install

# Install Flask and other dependencies
poetry self add poetry-plugin-export
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring


####################################################################################################
# .ENV STUFF
####################################################################################################

touch .env

# Update .env file
if ! egrep -q '^SECRET_KEY=' .env; then
    echo 'Generating new secret key'
    SECRET_KEY=$(openssl rand -hex 32)
    echo "SECRET_KEY=$SECRET_KEY" >> .env
fi

if ! egrep -q '^ENCRYPTION_KEY=' .env; then
    echo 'Generating new secret key'
    ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> .env
fi

if ! egrep -q '^DB_NAME=' .env; then
    echo 'Setting DB name'
    DB_NAME=$(whiptail --inputbox "Enter the database name" 8 39 "hushlinedb" --title "Database Name" 3>&1 1>&2 2>&3)
    echo "DB_NAME=$DB_NAME" >> .env
fi

if ! egrep -q '^DB_USER=' .env; then
    echo 'Setting DB user'
    DB_USER=$(whiptail --inputbox "Enter the database username" 8 39 "hushlineuser" --title "Database Username" 3>&1 1>&2 2>&3)
    echo "DB_USER=$DB_USER" >> .env
fi

if ! egrep -q '^DB_PASS=' .env; then
    echo 'Setting DB password'
    DB_PASS=$(whiptail --inputbox "Enter the database username" 8 39 "hushlineuser" --title "Database Username" 3>&1 1>&2 2>&3)
    echo "DB_PASS=$DB_PASS" >> .env
fi

if ! grep -q '^HUSHLINE_DEBUG_OPTS=' .env; then
    echo 'Setting HUSHLINE_DEBUG_OPTS to 0'
    echo "HUSHLINE_DEBUG_OPTS=0" >> .env
fi

if ! egrep -q '^SQLALCHEMY_DATABASE_URI=' .env; then
    echo 'Setting SQLALCHEMY_DATABASE_URI'
    # It's assumed DB_NAME, DB_USER, DB_PASS have been already captured above
    echo "SQLALCHEMY_DATABASE_URI=mysql+pymysql://$DB_USER:$DB_PASS@localhost/$DB_NAME" >> .env
fi

if ! egrep -q '^REGISTRATION_CODES_REQUIRED=' .env; then
    # Ask the user if registration should require codes and directly update the .env file
    if whiptail --title "Require Registration Codes" --yesno "Do you want to require registration codes for new users?" 8 78; then
        echo "Requiring registration codes for new users..."
        echo "REGISTRATION_CODES_REQUIRED=True" >> .env
    else
        echo "Not requiring registration codes for new users..."
        echo "REGISTRATION_CODES_REQUIRED=False" >> .env
    fi
fi

chmod 600 .env


####################################################################################################
# TOR STUFF
####################################################################################################

# Check if the torrc file contains specific configuration for your domain
if grep -q "$DOMAIN_CONFIG" "$TORRC_PATH"; then
    echo "Tor configuration for $DOMAIN already exists in $TORRC_PATH. Skipping configuration."
else
    echo "Adding Tor configuration for $DOMAIN to $TORRC_PATH..."
    echo -e "\n$DOMAIN_CONFIG" >> "$TORRC_PATH"
    echo "HiddenServicePort 80 unix:/var/www/html/$DOMAIN/hushline-hosted.sock" >> "$TORRC_PATH"
    # Restart Tor to apply new configuration
    systemctl restart tor

    # Restart Tor service
    systemctl restart tor.service
    sleep 10
fi

ONION_ADDRESS=$(cat /var/lib/tor/"$DOMAIN"/hostname)
SAUTEED_ONION_ADDRESS=$(echo "$ONION_ADDRESS" | tr -d '.')


####################################################################################################
# NGINX STUFF
####################################################################################################

# Check if hushline.nginx exists in /etc/nginx/sites-available/
if [ ! -f "$NGINX_SITE_PATH" ]; then
    echo "Nginx site configuration does not exist, copying template and updating placeholders..."

    # Copy the Nginx site configuration template
    cp files/hushline.nginx $NGINX_SITE_PATH

    # Copy the Nginx main configuration template
    cp files/nginx.conf $NGINX_CONF_PATH

    # Replace placeholders in the Nginx site configuration
    sed -i "s/\$DOMAIN/$DOMAIN/g" $NGINX_SITE_PATH
    sed -i "s/\$ONION_ADDRESS/$ONION_ADDRESS/g" $NGINX_SITE_PATH
    sed -i "s/\$SAUTEED_ONION_ADDRESS/$SAUTEED_ONION_ADDRESS/g" $NGINX_SITE_PATH

    echo "Nginx configuration updated successfully."

    ln -sf $NGINX_SITE_PATH /etc/nginx/sites-enabled/
    nginx -t && systemctl restart nginx
    
    if [ -e "/etc/nginx/sites-enabled/default" ]; then
        rm /etc/nginx/sites-enabled/default
    fi
    if nginx -t; then
        systemctl restart nginx
    else
        error_exit
    fi
else
    echo "Nginx site configuration already exists."
fi


####################################################################################################
# LET'S ENCRYPT
####################################################################################################

# Check if the SSL certificate directory for the domain exists
if [ ! -d "/etc/letsencrypt/live/"$DOMAIN"/" ]; then
    echo "SSL certificate directory for $DOMAIN does not exist. Obtaining SSL certificate..."
    whiptail --msgbox --title "Instructions" "\nPlease ensure that your DNS records are correctly set up before proceeding:\n\nAdd an A record with the name: @ and content: $SERVER_IP\n* Add a CNAME record with the name $SAUTEED_ONION_ADDRESS.$DOMAIN and content: $DOMAIN\n* Add a CAA record with the name: @ and content: 0 issue \"letsencrypt.org\"\n" 14 "$WIDTH"
    
    # Request the certificates
    echo "⏲️  Waiting 30 seconds for DNS to update..."
    sleep 30

    certbot --nginx -d "$DOMAIN" -d "$SAUTEED_ONION_ADDRESS.$DOMAIN" --agree-tos --non-interactive --no-eff-email --email "$EMAIL"
    (crontab -l 2>/dev/null; echo "30 2 * * 1 /usr/bin/certbot renew --quiet") | crontab -
    echo "✅ Automatic HTTPS certificates configured."

    # Enable IPv6 in Nginx configuration
    sed -i '/listen 80;/a \    listen [::]:80;' "$$NGINX_SITE_PATH"
    sed -i '/listen 443 ssl;/a \    listen [::]:443 ssl;' "$$NGINX_SITE_PATH"
    echo "✅ IPv6 configuration appended to Nginx configuration file."

    # Append OCSP Stapling configuration for SSL
    sed -i "/listen \[::\]:443 ssl;/a \    ssl_stapling on;\n    ssl_stapling_verify on;\n    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;\n    resolver 9.9.9.9 1.1.1.1 valid=300s;\n    resolver_timeout 5s;\n    ssl_session_cache shared:SSL:10m;" "$NGINX_CONF"
    echo "✅ OCSP Stapling, SSL Session, and Resolver Timeout added."

    # Test the Nginx configuration and reload if successful
    nginx -t && systemctl reload nginx || echo "Error: Nginx configuration test failed, please check the configuration."
else
    echo "SSL certificate directory for $DOMAIN already exists. Skipping SSL certificate acquisition."
fi


####################################################################################################
# DATABASE STUFF
####################################################################################################

# Add SSL keys to mariadb
mkdir -p /etc/mariadb/ssl

cp /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem /etc/mariadb/ssl/
cp /etc/letsencrypt/live/"$DOMAIN"/privkey.pem /etc/mariadb/ssl/

chown mysql:mysql /etc/mariadb/ssl/fullchain.pem /etc/mariadb/ssl/privkey.pem
chmod 400 /etc/mariadb/ssl/fullchain.pem /etc/mariadb/ssl/privkey.pem

# Enable SSL for MQSQL
cp files/50-server.conf /etc/mysql/mariadb.conf.d/

# Check and append ssl_cert configuration if it doesn't exist
if ! grep -q '^ssl_cert=' "$MY_CNF"; then
    echo 'Appending ssl_cert configuration...'
    echo "ssl_cert=/etc/mariadb/ssl/fullchain.pem" >> "$MY_CNF"
fi

# Check and append ssl_key configuration if it doesn't exist
if ! grep -q '^ssl_key=' "$MY_CNF"; then
    echo 'Appending ssl_key configuration...'
    echo "ssl_key=/etc/mariadb/ssl/privkey.pem" >> "$MY_CNF"
fi

if ! systemctl is-active --quiet mariadb; then
    echo "MariaDB server is not running. Starting MariaDB server..."
    sudo systemctl start mariadb
    sudo systemctl enable mariadb
    echo "MariaDB server started and enabled to start at boot."
else
    echo "MariaDB server is already running."
fi

# Check if MariaDB/MySQL is installed
if mysql --version &> /dev/null; then
    echo "MySQL/MariaDB is installed."
    mysql_secure_installation
else
    echo "MySQL/MariaDB is not installed. Skipping mysql_secure_installation."
fi

# Check if MariaDB/MySQL service is running
if ! systemctl is-active --quiet mariadb; then
    echo "MariaDB/MySQL service is not running. Starting it now..."
    systemctl start mariadb
fi

# Prompt to run mysql_secure_installation for initial setup
echo "Running mysql_secure_installation to secure your MariaDB/MySQL installation."
mysql_secure_installation


####################################################################################################
# APPLICATION USER
####################################################################################################

# Create a dedicated user for running the application
if ! id "$HUSHLINE_USER" &>/dev/null; then
    echo "Creating a dedicated user: $HUSHLINE_USER..."
    useradd -r -s /bin/false -g $HUSHLINE_GROUP $HUSHLINE_USER
else
    echo "Dedicated user $HUSHLINE_USER already exists."
fi

# Adjust the ownership of the application directory
chown -R $HUSHLINE_USER:$HUSHLINE_GROUP /var/www/html/$DOMAIN


####################################################################################################
# UPGRADE DB
####################################################################################################

# Upgrade DB
export FLASK_APP=hushline:create_app
poetry run flask db upgrade

# Change owner and permissions
chown -R $HUSHLINE_USER:$HUSHLINE_GROUP /var/www/html/hushline

cp files/hushline-hosted.service /etc/systemd/system/hushline-hosted.service


####################################################################################################
# REDIS STUFF
####################################################################################################

if ! systemctl is-active --quiet redis-server; then
    echo "Redis server is not running. Starting Redis server..."
    sudo systemctl start redis-server
    sudo systemctl enable redis-server
    echo "Redis server started and enabled to start at boot."
else
    echo "Redis server is already running."
fi


####################################################################################################
# SERVICE FILE
####################################################################################################

# Extract ENCRYPTION_KEY from .env file
ENCRYPTION_KEY=$(grep 'ENCRYPTION_KEY=' .env | cut -d'=' -f2)

# Check if ENCRYPTION_KEY is already set in the service file, if not, add it after the last Environment= line
if ! grep -q 'Environment="ENCRYPTION_KEY=' "${SERVICE_FILE}"; then
    echo 'Updating encryption key in the service file...'
    sed -i "/Environment=/a Environment=\"ENCRYPTION_KEY=${ENCRYPTION_KEY}\"" "${SERVICE_FILE}"
fi

systemctl daemon-reload
systemctl enable hushline-hosted.service
systemctl start hushline-hosted.service
systemctl restart hushline-hosted.service


####################################################################################################
# MISC STUFF
####################################################################################################

# Unattended Upgrades
echo "Configuring unattended-upgrades..."

cp files/50unattended-upgrades /etc/apt/apt.conf.d/
cp files/20auto-upgrades /etc/apt/apt.conf.d/

systemctl start fail2ban
systemctl enable fail2ban

# Remove existing jail.local if it exists, then copy the new one
rm -f /etc/fail2ban/jail.local
cp files/jail.local /etc/fail2ban/

systemctl restart fail2ban