import sys
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pgpy
import warnings
from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

# Retrieve variables from system input
smtp_server = sys.argv[1]
smtp_port = sys.argv[2]
email_address = sys.argv[3]
email_password = sys.argv[4]
hushline_path = sys.argv[5]
onion_address = sys.argv[6]

def send_installation_complete_email(
    smtp_server, smtp_port, email, password, hushline_path, onion_address
):
    subject = "🎉 Blackbox Installation Complete"
    message = (
        "Blackbox has been successfully installed! In a moment, your device will reboot.\n\nYou can visit your tip line when you see \"Blackbox is running\" on your e-Paper display. If you can't immediately connect, don't panic; this is normal, as your device's information sometimes takes a few minutes to publish.\n\nYour Hush Line address is:\nhttp://"
        + onion_address
        + "\n\nTo send a message, enter your address into Tor Browser. To find information about your Hush Line, including tips for when to use it, visit: http://"
        + onion_address
        + "/info. If you still need to download Tor Browser, get it from https://torproject.org/download.\n\nHush Line is a free and open-source tool by Science & Design, Inc. Learn more about us at https://scidsg.org.\n\nIf you've found this resource useful, please consider making a donation at https://opencollective.com/scidsg."
    )

    # Load the public key from its path
    key_path = os.path.expanduser(
        hushline_path + "/public_key.asc"
    )  # Use os to expand the path
    with open(key_path, "r") as key_file:
        key_data = key_file.read()
        PUBLIC_KEY, _ = pgpy.PGPKey.from_blob(key_data)

    # Encrypt the message
    encrypted_message = str(PUBLIC_KEY.encrypt(pgpy.PGPMessage.new(message)))

    # Construct the email
    msg = MIMEMultipart()
    msg["From"] = email
    msg["To"] = email
    msg["Subject"] = subject
    msg.attach(MIMEText(encrypted_message, "plain"))

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(email, password)
        server.sendmail(email, [email], msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

# Actually send the installation confirmation email
send_installation_complete_email(
    smtp_server, smtp_port, email_address, email_password, hushline_path, onion_address
)