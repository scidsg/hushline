#!/bin/bash

####################################################################################################

# BEGIN SCRIPT

# This section starts the installer, ensuring it runs with root privileges for necessary system 
# changes, setting strict error handling to immediately halt on errors, and introducing Hush Line 
# with ASCII art and a brief description. An error_exit function provides a fallback to gracefully 
# handle and report errors, ensuring a clear exit strategy if the script encounters issues during 
# execution.

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

# Here, the script prepares the environment for Hush Line by updating system packages and installing 
# necessary dependencies like Python, Nginx, and MariaDB. It checks for the presence of a specific 
# user and creates it if missing, ensuring the application runs under a dedicated account for 
# security. Additionally, Rust and Python's Poetry are installed to handle backend dependencies.

####################################################################################################

GIT="https://github.com/scidsg/hushline.git"
HUSHLINE_USER="hushlineuser"
HUSHLINE_GROUP="www-data"

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
    certbot \
    python3-certbot-nginx \
    libnginx-mod-http-geoip \
    ufw \
    fail2ban \
    redis \
    redis-server \
    apt-transport-https

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

# This segment of the script configures Hush Line's environment by dynamically creating a .env file 
# if it doesn't already exist. It populates this file with essential variables, including secret 
# keys for security, database connection details, and configuration options for debug and 
# registration codes. User inputs are gathered via whiptail dialogs for a friendly interface, 
# allowing for customized setup.

####################################################################################################

DB_NAME="${DB_NAME:-defaultdbname}"
DB_USER="${DB_USER:-defaultdbuser}"
DB_PASS="${DB_PASS:-defaultdbpass}"

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

# In this part, the script enhances Hush Line's privacy features by integrating it with the Tor 
# network. It adds the Tor package repository if it's not already present, ensuring access to the 
# latest versions directly from the Tor Project. This step includes verifying and adding the 
# repository's GPG key for secure package installations. Next, it configures Tor by appending a 
# custom hidden service directory and port configuration to the torrc file, making Hush Line 
# accessible via a .onion address.

####################################################################################################

TORRC_PATH="/etc/tor/torrc"
DOMAIN_CONFIG="HiddenServiceDir /var/lib/tor/hushline/"
DISTRIBUTION=$(lsb_release -cs)
REPO_URL="https://deb.torproject.org/torproject.org ${DISTRIBUTION} main"
REPO_SRC_URL="https://deb.torproject.org/torproject.org ${DISTRIBUTION} main"
GPG_KEY_URL="https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc"
KEYRING_PATH="/usr/share/keyrings/tor-archive-keyring.gpg"
OVERRIDE_DIR="/etc/systemd/system/tor@default.service.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/override.conf"

# Enable Tor Package Repo
# Check if the Tor repository is already in the sources.list or sources.list.d/
if ! grep -Rq "^deb \[signed-by=/usr/share/keyrings/tor-archive-keyring.gpg\] ${REPO_URL}$" /etc/apt/sources.list /etc/apt/sources.list.d/*; then
    echo "deb [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] ${REPO_URL}" | tee /etc/apt/sources.list.d/tor.list
    echo "deb-src [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] ${REPO_SRC_URL}" | tee -a /etc/apt/sources.list.d/tor.list
    echo "✅ Added the Tor repository..."
else
    echo "👍 Tor repository already exists."
fi

# Check if the GPG keyring already exists
if [ ! -f "$KEYRING_PATH" ]; then
    wget -qO- "$GPG_KEY_URL" | gpg --dearmor | tee "$KEYRING_PATH" >/dev/null
    apt update
    apt install -y tor deb.torproject.org-keyring
    echo "✅ Added the Tor GPG key and installed Tor."
else
    echo "👍 Tor GPG keyring already exists."
fi

# Check if the torrc file contains specific configuration for your domain
if grep -q "$DOMAIN_CONFIG" "$TORRC_PATH"; then
    echo "👍 Tor configuration for Hush Line already exists in $TORRC_PATH. Skipping configuration."
else
    echo -e "\n$DOMAIN_CONFIG" >> "$TORRC_PATH"
    echo "HiddenServicePort 80 unix:/var/www/html/hushline/hushline.sock" >> "$TORRC_PATH"
    echo "✅ Added Tor configuration for Hush Line to $TORRC_PATH."

    # Restart Tor to apply new configuration
    systemctl restart tor

    # Restart Tor service
    systemctl restart tor.service
    sleep 10
fi

# Create an override file with an ExecStartPost command and restart on failure for the Tor service
if [ ! -d "$OVERRIDE_DIR" ]; then
    echo "Creating systemd override directory for Tor..."
    mkdir -p "$OVERRIDE_DIR"
    cp files/override.conf "$OVERRIDE_FILE"
    systemctl daemon-reload
    systemctl restart tor@default.service
    echo "✅ Systemd override directory created and Tor service restarted."
else
    echo "👍 Systemd override directory for Tor already exists."
fi

####################################################################################################

# NGINX STUFF

# In this section, the script configures Nginx to serve Hush Line, setting up a reverse proxy to 
# forward requests to the application. It involves copying a predefined Nginx configuration file, 
# replacing placeholders with actual domain names and paths, and ensuring Nginx recognizes the new 
# site configuration by linking it into the sites-enabled directory. This process also includes a 
# verification step using nginx -t to ensure the configuration is correct before attempting to 
# restart Nginx.

####################################################################################################

DOMAIN="test.ourdemo.app"
NGINX_SITE_PATH="/etc/nginx/sites-available/hushline.nginx"
NGINX_CONF_PATH="/etc/nginx/nginx.conf"
ONION_ADDRESS=$(cat /var/lib/tor/hushline/hostname)
SAUTEED_ONION_ADDRESS=$(echo "$ONION_ADDRESS" | tr -d '.')

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

# This section secures Hush Line's web traffic by obtaining SSL certificates from Let's Encrypt. It 
# prompts the user to ensure DNS records are set up correctly before proceeding with certificate 
# acquisition. Utilizing certbot with Nginx, the script automates the certificate request and 
# installation process, including configuring automatic renewal. Additionally, it adjusts Nginx 
# settings to support IPv6 and enhances SSL security with OCSP Stapling and resolver configurations. 

####################################################################################################

EMAIL="hushline@scidsg.org"
SERVER_IP=$(curl -s ifconfig.me)
WIDTH=$(tput cols)

# Check if the SSL certificate directory for the domain exists
if [ ! -d "/etc/letsencrypt/live/"$DOMAIN"/" ]; then
    echo "SSL certificate directory for $DOMAIN does not exist. Obtaining SSL certificate..."
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

# This portion of the script focuses on setting up and securing the MariaDB (or MySQL) database for 
# Hush Line. It involves creating a database and a user with the necessary permissions if they don't 
# already exist. The script also ensures SSL is enabled for database connections by placing SSL 
# certificates in the correct directory and updating the database configuration to use them. For 
# environments where MariaDB or MySQL is not yet secured, it runs the mysql_secure_installation 
# script. Additionally, the script checks if the MariaDB/MySQL service is active and starts it if 
# needed, ensuring the database is ready for Hush Line's data storage needs.

####################################################################################################

MY_CNF="/etc/mysql/my.cnf"
MYSQL_SECURED_FLAG="/etc/mysql/mysql_secure_installation_done"

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

# Check if MariaDB/MySQL is installed and if the secure installation has not been done yet
if mysql --version &> /dev/null; then
    echo "MySQL/MariaDB is installed."
    if [ ! -f "$MYSQL_SECURED_FLAG" ]; then
        echo "Running mysql_secure_installation..."
        mysql_secure_installation
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

# This section ensures the database schema is up to date for Hush Line. It checks for the existence 
# of a "migrations" directory to determine if database migrations need to be initialized with 
# Flask-Migrate. If the migrations are already set up, the script proceeds to apply any pending 
# migrations using Flask's db upgrade command, effectively upgrading the database schema to the 
# latest version required by Hush Line.

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

# Here, the script sets up Redis, a key-value store that Hush Line uses for caching and session 
# management, among other things. It checks if the Redis server is running and starts it if not, 
# also ensuring that it's enabled to start automatically on system boot. 

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

# This section deals with setting up a systemd service file for Hush Line, ensuring it starts 
# automatically at boot and can be managed with standard systemd commands like start, stop, and 
# restart. It updates the service file with the environment variable for the encryption key from the 
# .env file, if it's not already set. This setup allows Hush Line to run as a background service, 
# providing stability and ease of management.

####################################################################################################

SERVICE_FILE="/etc/systemd/system/hushline.service"
ENCRYPTION_KEY=$(grep 'ENCRYPTION_KEY=' .env | awk -F"ENCRYPTION_KEY=" '{print $2}')

# Check if ENCRYPTION_KEY is already set in the service file, if not, add it after the last Environment= line
if ! grep -q 'Environment="ENCRYPTION_KEY=' "${SERVICE_FILE}"; then
    echo 'Updating encryption key in the service file...'
    cp files/hushline.service /etc/systemd/system/hushline.service
    sed -i "/Environment=/a Environment=\"ENCRYPTION_KEY=${ENCRYPTION_KEY}\"" "${SERVICE_FILE}"
fi

####################################################################################################

# UNATTENDED UPGRADES

# This segment ensures that the system automatically installs security updates without manual 
# intervention. It configures unattended-upgrades by copying predefined configuration files that 
# specify which package categories should be automatically updated. This setup minimizes 
# vulnerabilities by ensuring timely application of security patches, maintaining system security 
# and stability over time.

####################################################################################################

# Unattended Upgrades
echo "Configuring unattended-upgrades..."
cp files/50unattended-upgrades /etc/apt/apt.conf.d/
cp files/20auto-upgrades /etc/apt/apt.conf.d/

####################################################################################################

# PERMISSIONS AND SERVICES

# In the final section, the script secures the Hush Line installation by setting appropriate file 
# permissions and ensuring all related services, such as Nginx and Redis, are correctly configured 
# and restarted. It meticulously adjusts ownership and permissions within the Hush Line directory 
# for security, updates the global Git configuration to include the Hush Line repository safely, and 
# ensures the systemd service for Hush Line is enabled and started, facilitating automatic startup 
# at boot.

####################################################################################################

# Git Permissions
chown -R $(whoami):$(whoami) /var/www/html/hushline
chmod -R 755 /var/www/html/hushline

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
systemctl enable hushline.service
systemctl restart hushline.service

# Reboot the system
echo "✅ Installation and configuration completed successfully."
echo "⏲️ Rebooting in 10 seconds..."
sleep 10
reboot