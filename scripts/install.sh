#!/bin/bash

# Welcome message and ASCII art
cat << "EOF"
  _    _           _       _      _            
 | |  | |         | |     | |    (_)           
 | |__| |_   _ ___| |__   | |     _ _ __   ___ 
 |  __  | | | / __| '_ \  | |    | | '_ \ / _ \
 | |  | | |_| \__ \ | | | | |____| | | | |  __/
 |_|  |_|\__,_|___/_| |_| |______|_|_| |_|\___|
                                               
🤫 A free tool by Science & Design - https://scidsg.org
Your anonymous tip line and suggestion box. 

EOF
sleep 3

# Welcome Prompt
whiptail --title "🤫 Hush Line Installation" --msgbox "Hush Line provides a simple way to receive secure messages from sources, colleagues, clients, or patients.\n\nAfter installation, you'll have a private tip line hosted on your own server, secured with PGP, HTTPS, and available on a .onion address so anyone can message you, even from locations where the internet is censored.\n\nIf deploying to a public website, ensure your DNS settings point to this server." 16 64

OPTION=$(whiptail --title "Installation Type" --menu "How would you like to install Hush Line?" 15 60 4 \
"1" "Tor-only" \
"2" "Tor + Public Domain"  3>&1 1>&2 2>&3)

exitstatus=$?
if [ $exitstatus = 0 ]; then
    echo "Your chosen option:" $OPTION
    if [ $OPTION = "1" ]; then
        curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/install-tor-only.sh | bash
    elif [ $OPTION = "2" ]; then
        curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/main/scripts/install-public-plus-tor.sh | bash
    fi
else
    echo "You chose Cancel."
fi
