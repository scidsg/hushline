# Hush-Line
Hush-Line is a reasonably secure and anonymous tip line that you can set up on your own domain name.

![hush-cover](https://user-images.githubusercontent.com/28545431/228141667-89fbaeb8-8282-4f86-a575-bdb29f9ffe31.png)

## Easy Install

```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/master/install.sh | bash
```

![demo](https://user-images.githubusercontent.com/28545431/228141719-00e0a284-f694-4045-8707-9ec5ca3070d2.gif)

Requirements

- Debian-based Linux distribution (e.g. Ubuntu)
- git
- Python 3.6 or higher
- virtualenv
- pip
- certbot
- nginx
- whiptail

## Installation

Update and upgrade your system:

```
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove
```

Install required packages:

```
sudo apt-get -y install git python3 python3-venv python3-pip certbot python3-certbot-nginx nginx whiptail
```

## Clone the repository:

```
git clone https://github.com/scidsg/hush-line.git
```

## Create a virtual environment and install dependencies:

```
cd hush-line
python3 -m venv venv
source venv/bin/activate
pip3 install flask
pip3 install pgpy
pip3 install -r requirements.txt
```

## Create a systemd service:

```
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
```

```
systemctl enable hush-line.service
systemctl start hush-line.service
```

## Configure Nginx:

```
cat > /etc/nginx/sites-available/hush-line.nginx << EOL
server {
    listen 80;
    server_name YOUR_DOMAIN_NAME;
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
```

## Obtain SSL certificate:

```
certbot --nginx --agree-tos --non-interactive --email YOUR_EMAIL --agree-tos
```
