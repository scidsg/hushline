from flask import Flask, render_template, request, jsonify
import os
import pgpy
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging

# setup a logger
log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
log.addHandler(handler)
log.info("Starting Hush Line")

app = Flask(__name__)

recipient_name = os.environ.get("RECIPIENT_NAME", None)
recipient_email = os.environ.get("RECIPIENT_EMAIL", None)
sender_email = os.environ.get("SENDER_EMAIL", None)
smtp_server = os.environ.get("SMTP_SERVER", None)
smtp_port = int(os.environ.get("SMTP_PORT", 465))
smtp_user = os.environ.get("SMTP_USER", None)
smtp_password = os.environ.get("SMTP_PASSWORD", None)
title = os.environ.get("TITLE", "🤫 Hush Line")
close_app_link = os.environ.get(
    "CLOSE_APP_LINK", "https://en.wikipedia.org/wiki/Tina_Turner"
)
pgp_enabled = os.environ.get("PGP_ENABLED", "true").lower() == "true"
pgp_filename = os.environ.get("PGP_FILENAME", "public_key.asc")

if not smtp_server or not smtp_port or not smtp_user or not smtp_password:
    log.warn(
        "Missing email notification configuration(s). Email notifications will not be sent."
    )

if pgp_enabled:
    # Load the public key into memory on startup
    with open(pgp_filename, "r") as key_file:
        key_data = key_file.read()
        PUBLIC_KEY, _ = pgpy.PGPKey.from_blob(
            key_data
        )  # Extract the key from the tuple

    def encrypt_message(message):
        encrypted_message = str(PUBLIC_KEY.encrypt(pgpy.PGPMessage.new(message)))
        return encrypted_message


@app.route("/")
def index():
    if pgp_enabled:
        recipient = f"{PUBLIC_KEY.userids[0].name}\n<{PUBLIC_KEY.userids[0].email}>"
        pgp_key_id = f"Key ID: {str(PUBLIC_KEY.fingerprint)[-8:]}"
        if PUBLIC_KEY.expires_at is not None:
            pgp_expires = f"Exp: {PUBLIC_KEY.expires_at.strftime('%Y-%m-%d')}"
        else:
            pgp_expires = f"Exp: never"
    else:
        recipient = f"{recipient_name} <{recipient_email}>"
        pgp_key_id = None
        pgp_expires = None

    return render_template(
        "index.html",
        title=title,
        close_app_link=close_app_link,
        recipient=recipient,
        pgp_enabled=pgp_enabled,
        pgp_key_id=pgp_key_id,
        pgp_expires=pgp_expires,
    )


@app.route("/save_message", methods=["POST"])
def save_message():
    message = request.form["message"]
    if pgp_enabled:
        message = encrypt_message(message)

    with open("messages.txt", "a") as f:
        f.write(message + "\n\n")
    return jsonify(send_email_notification(message))


def send_email_notification(message):
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = f"{recipient_name} <{recipient_email}>"
    msg["Subject"] = "🤫 New Hush Line Message Received"

    body = f"{message}"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return {"success": True}
    except Exception as e:
        log.error(f"Error sending email notification: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    app.run()
