#!/bin/bash

#Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Welcome message and ASCII art
cat <<"EOF"
  _    _           _       _      _            
 | |  | |         | |     | |    (_)           
 | |__| |_   _ ___| |__   | |     _ _ __   ___ 
 |  __  | | | / __| '_ \  | |    | | '_ \ / _ \
 | |  | | |_| \__ \ | | | | |____| | | | |  __/
 |_|  |_|\__,_|___/_| |_| |______|_|_| |_|\___|
                                               
🤫 A self-hosted, anonymous tip line.

A free tool by Science & Design - https://scidsg.org
EOF
sleep 3

# Update and upgrade non-interactively
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get -y dist-upgrade -o Dpkg::Options::="--force-confnew" && apt -y autoremove

# Install required packages
apt -y install whiptail curl git wget sudo

# Clone the repository in the user's home directory
cd $HOME
if [[ ! -d hushline ]]; then
    # If the hushline directory does not exist, clone the repository
    git clone https://github.com/scidsg/hushline.git
else
    # If the hushline directory exists, clean the working directory and pull the latest changes
    echo "The directory 'hushline' already exists, updating repository..."
    cd hushline
    git restore --source=HEAD --staged --worktree -- .
    git reset HEAD -- .
    git clean -fd .
    git config pull.rebase false
    git pull
    cd $HOME # return to HOME for next steps
fi

# "reset" the terminal window before running first whiptail prompt
reset

# Welcome Prompt
whiptail --title "🤫 Hush Line Installation" --msgbox "Hush Line provides a simple way to receive secure messages from sources, colleagues, clients, or patients.\n\nAfter installation, you'll have a private tip line hosted on your own server, secured with PGP, HTTPS, and available on a .onion address so anyone can message you, even from locations where the internet is censored.\n\nIf deploying to a public website, ensure your DNS settings point to this server." 16 64

OPTION=$(whiptail --title "Installation Type" --menu "How would you like to install Hush Line?" 15 60 4 \
    "1" "Tor-only" \
    "2" "Tor + Public Domain" 3>&1 1>&2 2>&3)

exitstatus=$?
if [ $exitstatus = 0 ]; then
    echo "Your chosen option:" $OPTION
    
    # Change to the user's home directory before accessing install-tor-only.sh
    cd $HOME
    
    if [ $OPTION = "1" ]; then
        chmod +x hushline/assets/scripts/install-tor-only.sh
        ./hushline/assets/scripts/install-tor-only.sh
    elif [ $OPTION = "2" ]; then
        chmod +x hushline/assets/scripts/install-public-plus-tor.sh
        ./hushline/assets/scripts/install-public-plus-tor.sh
    fi
else
    echo "You chose Cancel."
fi
