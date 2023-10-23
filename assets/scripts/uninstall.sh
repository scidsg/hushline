#!/bin/bash

# Uninstaller for Hushline

# Run as root
if [[ $EUID -ne 0 ]]; then
  echo "Script needs to run as root. Elevating permissions now."
  exec sudo /bin/bash "$0" "$@"
fi

# Ask user if they want to uninstall all packages
if (whiptail --title "Confirmation" --yesno "Do you want to uninstall Hush Line?" 10 60); then

    # Stop services
    systemctl stop hushline.service
    systemctl stop nginx
    systemctl stop tor.service
    systemctl stop fail2ban
    systemctl stop ufw

    # Disable services
    systemctl disable hushline.service
    systemctl disable nginx
    systemctl disable tor.service
    systemctl disable fail2ban
    systemctl disable ufw

    # Remove nginx configuration
    rm -f /etc/nginx/sites-enabled/hushline.nginx
    rm -f /etc/nginx/sites-available/hushline.nginx
    rm -f /etc/nginx/nginx.conf

    # Remove systemd service
    rm -f /etc/systemd/system/hushline.service

    # Remove environment files and hushline directory
    rm -rf /etc/hushline
    rm -rf ~/hushline  # or the appropriate directory where hushline was installed

    # Remove unattended-upgrades configurations
    rm -f /etc/apt/apt.conf.d/50unattended-upgrades
    rm -f /etc/apt/apt.conf.d/20auto-upgrades

    # Restore original torrc (assuming a backup was created)
    if [ -e /etc/tor/torrc.backup ]; then
        mv /etc/tor/torrc.backup /etc/tor/torrc
    fi

    # Restore original fail2ban config
    rm -f /etc/fail2ban/jail.local
    if [ -e /etc/fail2ban/jail.conf.backup ]; then
        mv /etc/fail2ban/jail.conf.backup /etc/fail2ban/jail.conf
    fi

    # Reset UFW rules (this will remove all rules and reset to default)
    echo "y" | ufw reset

    # Ask user if they want to uninstall packages
    if (whiptail --title "Uninstall Packages" --yesno "Do you want to uninstall the packages installed by Hushline? This could break other dependent application on your device." 10 60); then
        apt-get purge -y git python3 python3-venv python3-pip nginx tor libnginx-mod-http-geoip geoip-database unattended-upgrades gunicorn libssl-dev net-tools fail2ban ufw
        apt-get autoremove -y
    fi

    echo "Uninstallation complete."
else
    echo "Uninstallation cancelled."
    exit 0
fi

# Remove the custom bash functions and calls from /etc/bash.bashrc
sed -i '/display_status_indicator()/,/}/d' /etc/bash.bashrc
sed -i '/display_status_indicator/d' /etc/bash.bashrc

# Ask user if they want to reboot the system
if (whiptail --title "Reboot System" --yesno "Do you want to reboot your system now?" 10 60); then
    echo "Rebooting system..."
    reboot
else
    echo "You may want to reboot the system manually later to ensure all changes are applied."
    exit 0
fi

