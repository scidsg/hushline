#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

#Update and upgrade
apt update && apt -y dist-upgrade && apt -y autoremove

# Function to display error message and exit
error_exit() {
    echo "An error occurred during installation. Please check the output above for more details."
    exit 1
}

# Trap any errors and call the error_exit function
trap error_exit ERR

cd $HOME/hushline/templates
mv index.html index.html.old
wget https://raw.githubusercontent.com/scidsg/hushline/main/templates/index.html

cd $HOME/hushline/static
mv style.css style.css.old
wget https://raw.githubusercontent.com/scidsg/hushline/main/static/style.css

echo "
✅ Update complete!
                                               
Hush Line is a product by Science & Design. 
Learn more about us at https://scidsg.org.
Have feedback? Send us an email at hushline@scidsg.org."

systemctl restart hush-line

rm $HOME/hushline/static/style.css.old
rm $HOME/hushline/templates/index.html.old

# Disable the trap before exiting
trap - ERR
