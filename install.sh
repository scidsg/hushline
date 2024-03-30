#!/bin/bash

####################################################################################################
# VARIABLES
####################################################################################################

DOMAIN="test.ourdemo.app"
EMAIL="hushline@scidsg.org"
GIT="https://github.com/scidsg/hushline.git"
HUSHLINE_USER="hushlineuser"
HUSHLINE_GROUP="www-data"
SERVICE_FILE="/etc/systemd/system/hushline-hosted.service"
MY_CNF="/etc/mysql/my.cnf"
TORRC_PATH="/etc/tor/torrc"
DOMAIN_CONFIG="HiddenServiceDir /var/lib/tor/$DOMAIN/"
NGINX_SITE_PATH="/etc/nginx/sites-available/hushline.nginx"
NGINX_CONF_PATH="/etc/nginx/nginx.conf"
DB_NAME="${DB_NAME:-defaultdbname}"
DB_USER="${DB_USER:-defaultdbuser}"
DB_PASS="${DB_PASS:-defaultdbpass}"


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
    certbot \
    python3-certbot-nginx \
    libnginx-mod-http-geoip \
    ufw \
    fail2ban \
    redis \
    redis-server

cd /var/www/html
if [ ! -d hushline ]; then
    git clone $GIT
fi
cd hushline
git switch migrations
sleep 5

chmod +x install.sh

# Create a dedicated user for running the application
if ! id "$HUSHLINE_USER" &>/dev/null; then
    echo "Creating a dedicated user: $HUSHLINE_USER..."
    useradd -r -s /bin/false -g $HUSHLINE_GROUP $HUSHLINE_USER
    echo "✅ Dedicated user $HUSHLINE_USER created."
else
    echo "👍 Dedicated user $HUSHLINE_USER already exists."
fi

if ! command -v rustc &> /dev/null; then
    echo "Rust is not installed. Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
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

# Ensuring virtual environment binaries are executable only if necessary
echo "Checking and setting execute permissions on virtual environment binaries..."

for file in /var/www/html/hushline/venv/bin/*; do
    if [ ! -x "$file" ]; then
        echo "Setting execute permission on $file"
        chmod +x "$file"
        echo "✅ Execute permission set."
    else
        echo "👍 Permissions already set."
    fi
done

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
    DB_PASS=$(whiptail --passwordbox "Enter the database password" 8 39 "dbpassword" --title "Database Password" 3>&1 1>&2 2>&3)
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
    echo "👍 Tor configuration for $DOMAIN already exists in $TORRC_PATH. Skipping configuration."
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

    echo "✅ Nginx configuration updated successfully."

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
    echo "👍 Nginx site configuration already exists."
fi


####################################################################################################
# LET'S ENCRYPT
####################################################################################################

# Check if the SSL certificate directory for the domain exists
if [ ! -d "/etc/letsencrypt/live/"$DOMAIN"/" ]; then
    echo "SSL certificate directory for $DOMAIN does not exist. Obtaining SSL certificate..."
    SERVER_IP=$(curl -s ifconfig.me)
    WIDTH=$(tput cols)
    whiptail --msgbox --title "Instructions" "\nPlease ensure that your DNS records are correctly set up before proceeding:\n\nAdd an A record with the name: @ and content: $SERVER_IP\n* Add a CNAME record with the name $SAUTEED_ONION_ADDRESS.$DOMAIN and content: $DOMAIN\n* Add a CAA record with the name: @ and content: 0 issue \"letsencrypt.org\"\n" 14 "$WIDTH"
    
    # Request the certificates
    echo "⏲️  Waiting 30 seconds for DNS to update..."
    sleep 30

    certbot --nginx -d "$DOMAIN" -d "$SAUTEED_ONION_ADDRESS.$DOMAIN" --agree-tos --non-interactive --no-eff-email --email "$EMAIL"
    echo "30 2 * * 1 root /usr/bin/certbot renew --quiet" > /etc/cron.d/hushline_cert_renewal
    echo "✅ Automatic HTTPS certificates configured."

    # Enable IPv6 in Nginx configuration
    sed -i '/listen 80;/a \    listen [::]:80;' "$NGINX_SITE_PATH"
    sed -i '/listen 443 ssl;/a \    listen [::]:443 ssl;' "$NGINX_SITE_PATH"
    echo "✅ IPv6 configuration appended to Nginx configuration file."

    # Append OCSP Stapling configuration for SSL
    sed -i "/listen \[::\]:443 ssl;/a \    ssl_stapling on;\n    ssl_stapling_verify on;\n    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;\n    resolver 9.9.9.9 1.1.1.1 valid=300s;\n    resolver_timeout 5s;\n    ssl_session_cache shared:SSL:10m;" "$NGINX_SITE_PATH"
    echo "✅ OCSP Stapling, SSL Session, and Resolver Timeout added."

    # Test the Nginx configuration and reload if successful
    nginx -t && systemctl reload nginx || echo "Error: Nginx configuration test failed, please check the configuration."
else
    echo "👍 SSL certificate directory for $DOMAIN already exists. Skipping SSL certificate acquisition."
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
    systemctl start mariadb
    systemctl enable mariadb
    echo "✅ MariaDB server started and enabled to start at boot."
else
    echo "🏃‍➡️ MariaDB server is already running."
fi

# Check if MariaDB/MySQL is installed
# Define the path for the flag file
MYSQL_SECURED_FLAG="/etc/mysql/mysql_secure_installation_done"

# Check if MariaDB/MySQL is installed and if the secure installation has not been done yet
if mysql --version &> /dev/null; then
    echo "MySQL/MariaDB is installed."
    if [ ! -f "$MYSQL_SECURED_FLAG" ]; then
        echo "Running mysql_secure_installation..."
        mysql_secure_installation

        # After running mysql_secure_installation, create a flag file to indicate it's been done
        touch "$MYSQL_SECURED_FLAG"
        echo "✅ mysql_secure_installation is completed. This will not run again unless the flag file is removed."
    else
        echo "👍 mysql_secure_installation has already been run previously."
    fi
else
    echo "⚠️ MySQL/MariaDB is not installed. Skipping mysql_secure_installation."
fi


# Check if MariaDB/MySQL service is running
if ! systemctl is-active --quiet mariadb; then
    echo "MariaDB/MySQL service is not running. Starting it now..."
    systemctl start mariadb
fi

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

# Reload the systemd daemon and restart MariaDB to apply changes
systemctl daemon-reload
systemctl restart mariadb


####################################################################################################
# UPGRADE DB
####################################################################################################

# Check if the migrations folder does not exist
if [ ! -d "migrations" ]; then
    echo "Initializing database migrations..."
    poetry run flask db init
    echo "✅ Database migrations initialized..."
else
    echo "👍 Migrations already initialized."
fi

systemctl restart mariadb
sleep 5

# Upgrade DB
export FLASK_APP=hushline:create_app
poetry run flask db migrate
poetry run flask db upgrade


####################################################################################################
# REDIS STUFF
####################################################################################################

if ! systemctl is-active --quiet redis-server; then
    echo "Redis server is not running. Starting Redis server..."
    systemctl start redis-server
    systemctl enable redis-server
    echo "✅ Redis server started and enabled to start at boot."
else
    echo "🏃‍➡️ Redis server is already running."
fi


####################################################################################################
# SERVICE FILE
####################################################################################################

# Extract ENCRYPTION_KEY from .env file
ENCRYPTION_KEY=$(grep 'ENCRYPTION_KEY=' .env | awk -F"ENCRYPTION_KEY=" '{print $2}')

# Check if ENCRYPTION_KEY is already set in the service file, if not, add it after the last Environment= line
if ! grep -q 'Environment="ENCRYPTION_KEY=' "${SERVICE_FILE}"; then
    echo 'Updating encryption key in the service file...'
    cp files/hushline-hosted.service /etc/systemd/system/hushline-hosted.service
    sed -i "/Environment=/a Environment=\"ENCRYPTION_KEY=${ENCRYPTION_KEY}\"" "${SERVICE_FILE}"
fi


####################################################################################################
# MISC STUFF
####################################################################################################

# Git Permissions
chown -R $(whoami):$(whoami) /var/www/html/hushline
chmod -R 755 /var/www/html/hushline

# Unattended Upgrades
echo "Configuring unattended-upgrades..."

cp files/50unattended-upgrades /etc/apt/apt.conf.d/
cp files/20auto-upgrades /etc/apt/apt.conf.d/

# Only start and enable fail2ban if it isn't already running
if ! systemctl is-active --quiet fail2ban; then
    echo "Fail2Ban is not running. Starting and enabling Fail2Ban..."
    systemctl start fail2ban
    systemctl enable fail2ban
    echo "✅ Fail2Ban started and enabled."
else
    echo "🏃‍➡️ Fail2Ban is already running."
fi

# Remove existing jail.local if it exists, then copy the new one
rm -f /etc/fail2ban/jail.local
cp files/jail.local /etc/fail2ban/

systemctl restart fail2ban


####################################################################################################
# WRAPPING UP
####################################################################################################

# Ensuring the correct ownership and permissions for the application directory
echo "Setting correct permissions for the application directory..."
find /var/www/html/hushline -type d -exec chmod 750 {} \;
find /var/www/html/hushline -type f -exec chmod 640 {} \;

# Ensuring virtual environment binaries are executable
echo "Ensuring virtual environment binaries are executable..."
chmod +x /var/www/html/hushline/venv/bin/*
chown -R $HUSHLINE_USER:$HUSHLINE_GROUP /var/www/html/hushline

# Update the global Git configuration
git config --global --add safe.directory /var/www/html/hushline

# Restart and enable related services, including Gunicorn, ensuring they use the updated permissions
echo "Restarting and enabling services..."
systemctl daemon-reload
systemctl restart nginx
systemctl enable hushline-hosted.service
systemctl restart hushline-hosted.service

echo "Installation and configuration completed successfully."