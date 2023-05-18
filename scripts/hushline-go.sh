#!/bin/bash

# Welcome message and ASCII art
cat << "EOF"
    __  __                    __             __     _                         ______       
   / / / /  __  __   _____   / /_           / /    (_)   ____   ___          / ____/  ____ 
  / /_/ /  / / / /  / ___/  / __ \         / /    / /   / __ \ / _ \        / / __   / __ \
 / __  /  / /_/ /  (__  )  / / / /        / /___ / /   / / / //  __/       / /_/ /  / /_/ /
/_/ /_/   \__,_/  /____/  /_/ /_/        /_____//_/   /_/ /_/ \___/        \____/   \____/ 
                                                      
🤫 A free tool by Science & Design - https://scidsg.org
Your anonymous tip line and suggestion box. 

EOF
sleep 3

# Welcome Prompt
whiptail --title "E-Ink Display Setup" --msgbox "The e-paper hat communicates with the Raspberry Pi using the SPI interface, so you need to enable it.\n\nNavigate to \"Interface Options\" > \"SPI\" and select \"Yes\" to enable the SPI interface." 12 64
sudo raspi-config

# Install the necessary dependencies
sudo apt-get update 
sudo apt-get -y dist-upgrade
sudo apt-get -y install python3-pip fonts-dejavu python3-pillow unattended-upgrades

# Install the Adafruit EPD library
sudo pip3 install adafruit-circuitpython-epd qrcode pgpy requests python-gnupg

# Ask the user for the Hush Line address and PGP key address
HUSH_LINE_ADDRESS=$(whiptail --inputbox "What's the Hush Line address?" 8 78 --title "Hush Line address" 3>&1 1>&2 2>&3)
PGP_KEY_ADDRESS=$(whiptail --inputbox "What's the address for your PGP key?" 8 78 --title "PGP key address" 3>&1 1>&2 2>&3)

# Download the key and rename to public_key.asc
mkdir -p /home/pi/hush-line/
wget $PGP_KEY_ADDRESS -O /home/pi/hush-line/public_key.asc

# Write the Hush Line address and PGP key address to a config file
echo "HUSH_LINE_ADDRESS=$HUSH_LINE_ADDRESS" > /home/pi/hush-line/config.txt
echo "PGP_KEY_ADDRESS=$PGP_KEY_ADDRESS" >> /home/pi/hush-line/config.txt

# Create a new script to display status on the e-ink display
# Create the hush-line directory if it does not exist
cat > /home/pi/hush-line/app_status.py << EOL
import digitalio
import busio
import board
import qrcode
from adafruit_epd.ssd1680 import Adafruit_SSD1680
from PIL import Image, ImageDraw, ImageFont
import time
import textwrap
import pgpy
import requests
import gnupg
import datetime
import os

def display_splash_screen(epd, image_path, display_time):
    print(f'Displaying splash screen: {image_path}')
    image = Image.open(image_path).convert("L")

    target_height = int(epd.width * 0.75)
    height_ratio = target_height / image.height
    target_width = int(image.width * height_ratio)

    image = image.resize((target_width, target_height), Image.ANTIALIAS)
    image_bw = Image.new("L", (epd.height, epd.width), 255)  # "L" mode
    paste_x = (epd.height - target_width) // 2
    paste_y = (epd.width - target_height) // 2
    image_bw.paste(image, (paste_x, paste_y))

    image_bw = image_bw.rotate(-90, expand=True)

    epd.image(image_bw)
    epd.display()
    time.sleep(display_time)

def get_key_info(file_path):
    with open(file_path, "r") as f:
        key_data = f.read()
    key, _ = pgpy.PGPKey.from_blob(key_data)
    user_name = str(key.userids[0].name)
    user_email = str(key.userids[0].email)
    user_id = f"{user_name} <{user_email}>"
    key_id = key.fingerprint[-8:]
    exp_date = "No expiration"
    if key.expires_at is not None:
        exp_date = key.expires_at.strftime("%Y-%m-%d")
    return user_id, key_id, exp_date

user_id, key_id, exp_date = get_key_info("/home/pi/hush-line/public_key.asc")

with open("/home/pi/hush-line/config.txt") as f:
    lines = f.readlines()
hush_line_address = lines[0].split("=")[1].strip()
pgp_key_address = lines[1].split("=")[1].strip()

spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
ecs = digitalio.DigitalInOut(board.CE0)
dc = digitalio.DigitalInOut(board.D22)
rst = digitalio.DigitalInOut(board.D27)
busy = digitalio.DigitalInOut(board.D17)

display = Adafruit_SSD1680(
    122, 250, spi, cs_pin=ecs, dc_pin=dc, sramcs_pin=None, rst_pin=rst, busy_pin=busy
)
font = ImageFont.load_default()

last_seen_hush_line = datetime.datetime.now()

# Display splash screen
script_path = os.path.dirname(os.path.realpath(__file__))
splash_screen_path = os.path.join(script_path, '/home/pi/hush-line/splash-sm.png')  # replace with the path to your splash screen
display_splash_screen(display, splash_screen_path, 3)  # display splash screen for 3 seconds

while True:
    display.fill(0xFF)
    display.display()
    image = Image.new("L", (display.height, display.width), color=255)
    draw = ImageDraw.Draw(image)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=1,
    )
    qr.add_data(hush_line_address)
    qr.make(fit=True)
    qr_img = qr.make_image(fill="black", back_color="white").convert("L")
    desired_height = 120
    aspect_ratio = qr_img.width / qr_img.height
    new_width = int(desired_height * aspect_ratio)
    qr_img = qr_img.resize((new_width, desired_height))
    qr_x = 0
    qr_y = 0
    image.paste(qr_img, (qr_x, qr_y))

    instruction_text = "Scan the QR code to send a private Hush Line message."
    wrapped_instruction = textwrap.wrap(instruction_text, width=18)
    instruction_image = Image.new("L", (display.height - qr_img.height, display.width), color=255)
    instruction_draw = ImageDraw.Draw(instruction_image)
    current_height = 0
    for line in wrapped_instruction:
        instruction_draw.text((0, current_height), line, font=font, fill=0)
        current_height += font.getsize(line)[1]

    info_text = f"{user_id}\nKey ID: {key_id}\nExp: {exp_date}"
    wrapped_text = textwrap.wrap(info_text, width=18)

    text_image = Image.new("L", (display.height - qr_img.height, display.width), color=255)
    text_draw = ImageDraw.Draw(text_image)

    current_height = 0
    for line in wrapped_text:
        text_draw.text((0, current_height), line, font=font, fill=0)
        current_height += font.getsize(line)[1]

    instruction_x = qr_img.width + 10
    instruction_y = 5  
    image.paste(instruction_image, (instruction_x, instruction_y)) 

    gap = 40

    text_x = instruction_x  
    text_y = instruction_y + gap  
    image.paste(text_image, (text_x, text_y)) 

    try:
        response = requests.get(hush_line_address, timeout=10)
        print(f'Response status code: {response.status_code}')  # print status code
        if response.status_code == 200:
            last_seen_hush_line = datetime.datetime.now()
    except requests.exceptions.RequestException as e:
        print(f'Request exception: {e}')  # print exception

    time_since_last_seen = datetime.datetime.now() - last_seen_hush_line
    time_since_last_seen_min = int(time_since_last_seen.total_seconds() / 60)

    if time_since_last_seen_min == 0:
        last_seen_text = "Last seen now"
    elif time_since_last_seen_min < 60:
        last_seen_text = f"Last seen {time_since_last_seen_min}m ago"
    elif time_since_last_seen_min < 24 * 60:
        hours = time_since_last_seen_min // 60
        last_seen_text = f"Last seen {hours}h ago"
    else:
        days = time_since_last_seen_min // (24 * 60)
        last_seen_text = f"Last seen {days}d ago"

    # Calculate remaining height for status_image
    remaining_height = display.height - qr_img.height - instruction_image.height - text_image.height - 20
    if remaining_height < 0:
        remaining_height = 10  # assign a minimum height

    # Create a new image for the last_seen_text
    font_info = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf', 10)
    status_image = Image.new("L", (display.width, remaining_height), color=255)
    status_draw = ImageDraw.Draw(status_image)

    # Calculate the width and height of the text
    text_width, text_height = status_draw.textsize(last_seen_text, font=font_info)

    # Set padding for top
    top_padding = (status_image.height - text_height) // 2  # Keep vertical centering

    # Draw the text starting from the left margin (left-justified)
    status_draw.text((0, top_padding), last_seen_text, font=font_info, fill=0)

    # Position status_image correctly
    status_x = qr_img.width + 9
    status_y = 102
    image.paste(status_image, (status_x, status_y))

    image = image.rotate(-90, expand=True)

    display.image(image)
    display.display()

    time.sleep(60)
EOL

# Clear display before shutdown
cat > /etc/systemd/system/app-status.service << EOL
[Unit]
Description=Hush Line Display Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/hush-line/app_status.py
WorkingDirectory=/home/pi/hush-line
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
EOL

sudo systemctl start app-status
sudo systemctl enable app-status

# Download splash screen image
cd /home/pi/hush-line
wget https://raw.githubusercontent.com/scidsg/brand-resources/main/logos/splash-sm.png

# Enable the "security" and "updates" repositories
sudo sed -i 's/\/\/\s\+"\${distro_id}:\${distro_codename}-security";/"\${distro_id}:\${distro_codename}-security";/g' /etc/apt/apt.conf.d/50unattended-upgrades
sudo sed -i 's/\/\/\s\+"\${distro_id}:\${distro_codename}-updates";/"\${distro_id}:\${distro_codename}-updates";/g' /etc/apt/apt.conf.d/50unattended-upgrades
sudo sed -i 's|//\s*Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";|Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";|' /etc/apt/apt.conf.d/50unattended-upgrades
sudo sed -i 's|//\s*Unattended-Upgrade::Remove-Unused-Dependencies "true";|Unattended-Upgrade::Remove-Unused-Dependencies "true";|' /etc/apt/apt.conf.d/50unattended-upgrades

sudo dpkg-reconfigure --priority=low unattended-upgrades

# Configure unattended-upgrades
echo 'Unattended-Upgrade::Automatic-Reboot "true";' | sudo tee -a /etc/apt/apt.conf.d/50unattended-upgrades
echo 'Unattended-Upgrade::Automatic-Reboot-Time "02:00";' | sudo tee -a /etc/apt/apt.conf.d/50unattended-upgrades

sudo systemctl restart unattended-upgrades
sudo apt-get -y autoremove

echo "Automatic updates have been installed and configured."

echo "✅ E-ink display configuration complete. Rebooting your Raspberry Pi..."
sleep 3

sudo reboot
