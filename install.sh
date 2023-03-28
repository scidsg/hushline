#!/bin/bash

#Update and upgrade
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove

# Install required packages
sudo apt-get -y install git python3 python3-venv python3-pip certbot python3-certbot-nginx nginx whiptail tor

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call the error_exit function
trap error_exit ERR

# Prompt user for domain name
DOMAIN=$(whiptail --inputbox "Enter your domain name:" 8 60 3>&1 1>&2 2>&3)

# Prompt user for email
EMAIL=$(whiptail --inputbox "Enter your email:" 8 60 3>&1 1>&2 2>&3)

# Check for valid domain name format
until [[ $DOMAIN =~ ^[a-zA-Z0-9][a-zA-Z0-9\.-]*\.[a-zA-Z]{2,}$ ]]; do
    DOMAIN=$(whiptail --inputbox "Invalid domain name format. Please enter a valid domain name:" 8 60 3>&1 1>&2 2>&3)
done

export DOMAIN

# Debug: Print the value of the DOMAIN variable
echo "Domain: ${DOMAIN}"

# Clone the repository
git clone https://github.com/scidsg/hush-line.git

# Create a virtual environment and install dependencies
cd hush-line
python3 -m venv venv
source venv/bin/activate
pip3 install flask
pip3 install pgpy
pip3 install -r requirements.txt

# Create a systemd service
cat > /etc/systemd/system/hush-line.service << EOL
[Unit]
Description=Tip-Line Web App
After=network.target

[Service]
User=root
WorkingDirectory=$PWD
ExecStart=$PWD/venv/bin/python3 $PWD/app.py
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
sudo tee /etc/tor/torrc << EOL
RunAsDaemon 1
HiddenServiceDir /var/lib/tor/hidden_service/
HiddenServicePort 80 127.0.0.1:80
HiddenServicePort 80 127.0.0.1:5000
EOL

# Restart Tor service
sudo systemctl restart tor.service

# Get the Onion address
ONION_ADDRESS=$(sudo cat /var/lib/tor/hidden_service/hostname)

# Enable the Tor hidden service
sudo ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

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
        add_header Onion-Location $ONION_ADDRESS$request_uri;
        add_header X-Content-Type-Options nosniff;
        add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'none'";
        add_header Permissions-Policy "geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=()";
        add_header Referrer-Policy "no-referrer";
        add_header X-XSS-Protection "1; mode=block";
}
EOL

if [ -e "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/hush-line.nginx /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx || error_exit

# Obtain SSL certificate
certbot --nginx --agree-tos --non-interactive --email ${EMAIL} --agree-tos -d $DOMAIN

# Set up cron job to renew SSL certificate
(crontab -l 2>/dev/null; echo "30 2 * * 1 /usr/bin/certbot renew --quiet") | crontab -

echo "Installation complete! The Tip-Line Web App should now be accessible at https://$DOMAIN and http://$ONION_ADDRESS"

# Disable the trap before exiting
