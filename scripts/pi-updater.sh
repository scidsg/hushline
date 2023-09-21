#!/bin/bash

#Update and upgrade
sudo apt update && sudo apt -y dist-upgrade && sudo apt -y autoremove

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call the error_exit function
trap error_exit ERR

cd /home/pi/hushline/templates
mv index.html index.html.old
wget https://raw.githubusercontent.com/scidsg/hushline/main/templates/index.html

cd /home/pi/hushline/static
mv style.css style.css.old
wget https://raw.githubusercontent.com/scidsg/hushline/main/static/style.css

echo "
✅ Update complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org."

sudo systemctl restart hush-line

rm /home/pi/hushline/static/style.css.old
rm /home/pi/hushline/templates/index.html.old

# Disable the trap before exiting
trap - ERR
