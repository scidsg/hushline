#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Welcome message
cat <<"EOF"
The QR installer is only intended for Tor-only installs on a local device.
EOF
sleep 3

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call error_exit function
trap error_exit ERR

# Create a virtual environment and install dependencies
cd hushline
python3 -m venv venv
source venv/bin/activate

nohup ./venv/bin/python3 blackbox-setup.py --host=0.0.0.0 &

# Launch Flask app for setup
nohup python3 blackbox-server-setup.py --host=0.0.0.0 &

sleep 5

# Display the QR code from the file
cat /tmp/qr_code.txt

echo "The Flask app for setup is running. Please complete the setup by navigating to http://hushline.local:5000/setup."

# Wait for user to complete setup form
while [ ! -f "/tmp/setup_config.json" ]; do
    sleep 5
done

# Read the configuration
EMAIL=$(jq -r '.email' /tmp/setup_config.json)
NOTIFY_SMTP_SERVER=$(jq -r '.smtp_server' /tmp/setup_config.json)
NOTIFY_PASSWORD=$(jq -r '.password' /tmp/setup_config.json)
NOTIFY_SMTP_PORT=$(jq -r '.smtp_port' /tmp/setup_config.json)
PGP_KEY_ADDRESS=$(jq -r '.pgp_key_address' /tmp/setup_config.json)

# Kill the Flask setup process
pkill -f setup_server_beta.py

# Download the public PGP key and rename to public_key.asc
wget $PGP_KEY_ADDRESS -O $PWD/public_key.asc

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

deactivate

# Disable the trap before exiting
trap - ERR

# Configure Display
# Create a new script to display status on the e-ink display
cat >/home/pi/hushline/display_status.py <<EOL
import os
import sys
import time
import textwrap
import qrcode
import requests
import gnupg
import traceback
from waveshare_epd import epd2in7
from PIL import Image, ImageDraw, ImageFont
from PIL import ImageOps
print(Image.__version__)

def display_splash_screen(epd, image_path, display_time):
    print(f'Displaying splash screen: {image_path}')
    image = Image.open(image_path).convert("L")

    target_height = int(epd.width * 0.75)
    height_ratio = target_height / image.height
    target_width = int(image.width * height_ratio)

    image = image.resize((target_width, target_height), Image.BICUBIC)
    image_bw = Image.new("1", (epd.height, epd.width), 255)
    paste_x = (epd.height - target_width) // 2
    paste_y = (epd.width - target_height) // 2
    image_bw.paste(image, (paste_x, paste_y))

    epd.display(epd.getbuffer(image_bw))
    time.sleep(display_time)
    epd.init()

def get_onion_address():
    with open('/var/lib/tor/hidden_service/hostname', 'r') as f:
        return f.read().strip()

def get_service_status():
    status = os.popen('systemctl is-active hush-line.service').read().strip()
    if status == 'active':
        return '✔ Hush Line is running'
    else:
        return '⨯ Hush Line is not running'

def display_status(epd, status, onion_address, name, email, key_id, expires):
    print(f'Displaying status: {status}, Onion address: {onion_address}')
    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    font_status = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 13)

    x_pos_status = 10
    y_pos_status = 10
    draw.text((x_pos_status, y_pos_status), status, font=font_status, fill=0)

    # Add the new text
    font_instruction = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 11)
    instruction_text = "Scan the QR code and open the link in Tor Browser to send a private message:"
    y_pos_instruction = y_pos_status + font_status.getbbox(status)[3] + 7
    max_width = epd.height - 20
    chars_per_line = max_width // font_instruction.getbbox('A')[2]
    wrapped_instruction = textwrap.wrap(instruction_text, width=40)
    for line in wrapped_instruction:
        draw.text((x_pos_status, y_pos_instruction), line, font=font_instruction, fill=0)
        y_pos_instruction += font_instruction.getbbox(wrapped_instruction[-1])[3] - font_instruction.getbbox(wrapped_instruction[-1])[1] + 5

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=3,
        border=2,
    )
    qr.add_data(f'http://{onion_address}')
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")

    # Calculate available height for QR code
    max_qr_height = epd.width - (y_pos_instruction + (font_instruction.getbbox(wrapped_instruction[-1])[3] - font_instruction.getbbox(wrapped_instruction[-1])[1]))

    width_scale_factor = max_qr_height / qr_img.width
    height_scale_factor = max_qr_height / qr_img.height

    new_size = (int(qr_img.width * width_scale_factor), int(qr_img.height * height_scale_factor))
    resized_qr_img = qr_img.resize(new_size, Image.NEAREST)

    y_pos_instruction += font_instruction.getbbox(wrapped_instruction[-1])[3] - font_instruction.getbbox(wrapped_instruction[-1])[1] + 5
    x_pos = x_pos_status - 3
    y_pos = y_pos_instruction - 12

    # Paste the QR code to the image
    image.paste(resized_qr_img, (x_pos, y_pos))

    # Calculate the starting position for the PGP information text
    x_pos_info = x_pos + resized_qr_img.width + 10

    font_info = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 11)

    # Change this line to a fixed value
    y_pos_info = 75  # initialize y_pos_info here before usage

    font_info = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 11)
    # y_pos_info = y_pos_instruction + new_size[1] + 5  # initialize y_pos_info here before usage

    # Display the PGP owner information
    max_width = epd.height - x_pos_info - 5
    chars_per_line = max_width // (font_info.getbbox('A')[2] - font_info.getbbox('A')[0])

    pgp_info = f'{name} <{email}>\nKey ID: {key_id[-8:]}\nExp: {time.strftime("%Y-%m-%d", time.gmtime(int(expires)))}'
    wrapped_pgp_info = []

    for line in pgp_info.split('\n'):
        wrapped_pgp_info.extend(textwrap.wrap(line, width=chars_per_line))

    line_spacing = 2
    empty_line_spacing = 0
    for i, line in enumerate(wrapped_pgp_info):
        draw.text((x_pos_info, y_pos_info), line, font=font_info, fill=0)
        if i < len(wrapped_pgp_info) - 1 and wrapped_pgp_info[i + 1] == '':
            y_pos_info += font_info.getbbox(line)[3] + empty_line_spacing
        else:
            y_pos_info += font_info.getbbox(line)[3] + line_spacing

    # Rotate the image by 90 degrees for landscape mode
    image_rotated = image.rotate(90, expand=True)

    epd.display(epd.getbuffer(image_rotated))

def get_pgp_owner_info(file_path):
    with open(file_path, 'r') as f:
        key_data = f.read()

    gpg = gnupg.GPG()
    imported_key = gpg.import_keys(key_data)
    fingerprint = imported_key.fingerprints[0]
    key = gpg.list_keys(keys=fingerprint)[0]

    uids = key['uids'][0].split()
    name = ' '.join(uids[:-1])
    email = uids[-1].strip('<>')
    key_id = key['keyid']
    expires = key['expires']

    return name, email, key_id, expires

def clear_screen(epd):
    print("Clearing the screen")
    image = Image.new('1', (epd.height, epd.width), 255)
    image_rotated = image.rotate(90, expand=True)
    epd.display(epd.getbuffer(image_rotated))
    epd.sleep()

def main():
    print("Starting main function")
    epd = epd2in7.EPD()
    epd.init()
    print("EPD initialized")

    # Display splash screen
    splash_image_path = "/home/pi/hushline/splash.png"
    display_splash_screen(epd, splash_image_path, 3)

    pgp_owner_info_url = "/home/pi/hushline/public_key.asc"

    try:
        while True:
            status = get_service_status()
            print(f'Service status: {status}')
            onion_address = get_onion_address()
            print(f'Onion address: {onion_address}')
            name, email, key_id, expires = get_pgp_owner_info(pgp_owner_info_url)
            display_status(epd, status, onion_address, name, email, key_id, expires)
            time.sleep(300)
    except KeyboardInterrupt:
        clear_screen(epd)
        print('Exiting...')
        sys.exit(0)
    except Exception:
        clear_screen(epd)
        print(f"Unexpected error:", traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    print("Starting display_status script")
    try:
            main()
    except KeyboardInterrupt:
        print('Exiting...')
        sys.exit(0)
EOL

# Create a new script to display status on the e-ink display
cat >/home/pi/hushline/clear_display.py <<EOL
import sys
from waveshare_epd import epd2in7
from PIL import Image

def clear_screen(epd):
    print("Clearing the screen")
    image = Image.new('1', (epd.height, epd.width), 255)
    image_rotated = image.rotate(90, expand=True)
    epd.display(epd.getbuffer(image_rotated))
    epd.sleep()

def main():
    print("Starting clear_display script")
    epd = epd2in7.EPD()
    epd.init()
    clear_screen(epd)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
EOL

# Clear display before shutdown
cat >/etc/systemd/system/clear-display.service <<EOL
[Unit]
Description=Clear e-Paper display before shutdown
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/pi/hushline/clear_display.py
TimeoutStartSec=0

[Install]
WantedBy=halt.target reboot.target shutdown.target
EOL
sudo systemctl daemon-reload
sudo systemctl enable clear-display.service

# Add a line to the .bashrc to run the display_status.py script on boot
if ! grep -q "sudo python3 /home/pi/hushline/display_status.py" /home/pi/.bashrc; then
    echo "sudo python3 /home/pi/hushline/display_status.py &" >>/home/pi/.bashrc
fi

# Download splash screen image
cd /home/pi/hushline
wget https://raw.githubusercontent.com/scidsg/hushline-assets/main/images/splash.png

echo "✅ E-ink display configuration complete. Rebooting your Raspberry Pi..."
sleep 3

sudo systemctl disable blackbox-installer.service

sudo reboot