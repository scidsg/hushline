#!/bin/bash

# Welcome message and ASCII art
cat << "EOF"                                                        
                                                            
   __             _____      __      _____      __    _ __  
 /'__`\  _______ /\ '__`\  /'__`\   /\ '__`\  /'__`\ /\`'__\
/\  __/ /\______\\ \ \L\ \/\ \L\.\_ \ \ \L\ \/\  __/ \ \ \/ 
\ \____\\/______/ \ \ ,__/\ \__/.\_\ \ \ ,__/\ \____\ \ \_\ 
 \/____/           \ \ \/  \/__/\/_/  \ \ \/  \/____/  \/_/ 
                    \ \_\              \ \_\                
                     \/_/               \/_/                
A free tool by Science & Design - https://scidsg.org

Make it easy for people around you to discover and use your Hush Line instance.

EOF
sleep 3

# Install required packages for e-ink display
apt update
apt-get -y dist-upgrade
apt-get install -y python3-pip whiptail

# Welcome Prompt
whiptail --title "E-Ink Display Setup" --msgbox "The e-paper hat communicates with the Raspberry Pi using the SPI interface, so you need to enable it.\n\nNavigate to \"Interface Options\" > \"SPI\" and select \"Yes\" to enable the SPI interface." 12 64
sudo raspi-config

# Install Waveshare e-Paper library
git clone https://github.com/waveshare/e-Paper.git
pip3 install ./e-Paper/RaspberryPi_JetsonNano/python/
pip3 install qrcode[pil]
pip3 install requests python-gnupg


# Install other Python packages
pip3 install RPi.GPIO spidev
apt-get -y autoremove

# Enable SPI interface
if ! grep -q "dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
    echo "SPI interface enabled."
else
    echo "SPI interface is already enabled."
fi

# Create a new script to display status on the e-ink display
cat > /home/pi/hush-line/display_status.py << EOL
import os
import sys
import time
import textwrap
import qrcode
import requests
import gnupg
from waveshare_epd import epd2in13_V3
from PIL import Image, ImageDraw, ImageFont
from PIL import ImageOps

def display_splash_screen(epd, image_path, display_time):
    print(f'Displaying splash screen: {image_path}')
    image = Image.open(image_path).convert("L")

    target_height = int(epd.width * 0.75)
    height_ratio = target_height / image.height
    target_width = int(image.width * height_ratio)

    image = image.resize((target_width, target_height), Image.ANTIALIAS)
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
        return '⛌ Hush Line is not running'

def display_status(epd, onion_address, name, email, key_id, expires):
    print(f'Onion address: {onion_address}')
    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

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

    # Resize QR code to full height
    qr_size = int(epd.height * 0.25)  # adjust the multiplier as needed
    resized_qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)

    x_pos_qr = 2
    y_pos_qr = 1
    image.paste(resized_qr_img, (x_pos_qr, y_pos_qr))

    # Calculate the starting position for the status, instruction and PGP information text
    x_pos_info = x_pos_qr + resized_qr_img.width + 6
    y_pos_info = y_pos_qr
    y_pos_instruction = y_pos_info

    # Add the new text
    font_instruction = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 11)
    instruction_text = "Scan the QR code and open the link in Tor Browser to send a private Hush Line message:"
    max_width = int(epd.width * 1.825)
    chars_per_line = max_width // font_instruction.getsize('A')[0]

    # make sure chars_per_line is at least 1
    chars_per_line = max(1, chars_per_line)

    # Use chars_per_line for the width
    wrapped_instruction = textwrap.wrap(instruction_text, width=chars_per_line)
    for line in wrapped_instruction:
        draw.text((x_pos_info, y_pos_instruction), line, font=font_instruction, fill=0)
        y_pos_instruction += font_instruction.getsize(line)[1]

    # Display the PGP owner information
    font_info = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 10)
    y_pos_info = y_pos_instruction + 10

    pgp_info = f'{name} <{email}>\nKey ID: {key_id[-8:]}\nExp: {time.strftime("%Y-%m-%d", time.gmtime(int(expires)))}'
    wrapped_pgp_info = []

    # Use the same chars_per_line for PGP info
    for line in pgp_info.split('\n'):
        wrapped_pgp_info.extend(textwrap.wrap(line, width=chars_per_line))

    line_spacing = 2
    empty_line_spacing = 0
    for i, line in enumerate(wrapped_pgp_info):
        draw.text((x_pos_info, y_pos_info), line, font=font_info, fill=0)
        if i < len(wrapped_pgp_info) - 1 and wrapped_pgp_info[i + 1] == '':
            y_pos_info += font_info.getsize(line)[1] + empty_line_spacing
        else:
            y_pos_info += font_info.getsize(line)[1] + line_spacing

    # Display the image on the e-ink display
    epd.display(epd.getbuffer(image.rotate(90, expand=True)))  # Rotate the image before displaying

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
    epd.display(epd.getbuffer(image.rotate(90, expand=True)))  # Rotate the image before displaying
    epd.sleep()

def main():
    print("Starting main function")
    epd = epd2in13_V3.EPD()
    epd.init()
    print("EPD initialized")

    # Display splash screen
    splash_image_path = "/home/pi/hush-line/splash-sm.png"
    display_splash_screen(epd, splash_image_path, 3)

    pgp_owner_info_url = "/home/pi/hush-line/public_key.asc"

    try:
        while True:
            onion_address = get_onion_address()
            print(f'Onion address: {onion_address}')
            name, email, key_id, expires = get_pgp_owner_info(pgp_owner_info_url)
            display_status(epd, onion_address, name, email, key_id, expires)
            time.sleep(60)
    except KeyboardInterrupt:
        clear_screen(epd)
        print('Exiting...')
        sys.exit(0)
    except Exception as e:
        clear_screen(epd)
        print(f"Unexpected error: {e}")
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
cat > /home/pi/hush-line/clear_display.py << EOL
import sys
from waveshare_epd import epd2in13_V3
from PIL import Image

def clear_screen(epd):
    print("Clearing the screen")
    image = Image.new('1', (epd.height, epd.width), 255)
    image_rotated = image.rotate(90, expand=True)
    epd.display(epd.getbuffer(image_rotated))
    epd.sleep()

def main():
    print("Starting clear_display script")
    epd = epd2in13_V3.EPD()
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
cat > /etc/systemd/system/clear-display.service << EOL
[Unit]
Description=Clear e-Paper display before shutdown
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/pi/hush-line/clear_display.py
TimeoutStartSec=0

[Install]
WantedBy=halt.target reboot.target shutdown.target
EOL
sudo systemctl daemon-reload
sudo systemctl enable clear-display.service

# Add a line to the .bashrc to run the display_status.py script on boot
if ! grep -q "sudo python3 /home/pi/hush-line/display_status.py" /home/pi/.bashrc; then
    echo "sudo python3 /home/pi/hush-line/display_status.py &" >> /home/pi/.bashrc
fi

# Download splash screen image
cd /home/pi/hush-line
wget https://raw.githubusercontent.com/scidsg/brand-resources/main/logos/splash.png

echo "✅ E-ink display configuration complete. Rebooting your Raspberry Pi..."
sleep 3

sudo reboot
