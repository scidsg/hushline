from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import pgpy
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging

# Initialize Flask-Limiter with Redis storage
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://localhost:6379",
)


def create_app():
    app = Flask(__name__)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Securely load the secret key from an environment variable or generate a random one
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

    # Setup a logger
    log = logging.getLogger(__name__)
    log.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    log.addHandler(handler)
    log.info("Starting Hush Line")

    # Attach the limiter to the app
    limiter.init_app(app)

    # Email configuration
    sender_email = os.environ.get("EMAIL", None)
    sender_password = os.environ.get("NOTIFY_PASSWORD", None)
    smtp_server = os.environ.get("NOTIFY_SMTP_SERVER", None)
    smtp_port = int(os.environ.get("NOTIFY_SMTP_PORT", 0))

    if not sender_email or not sender_password or not smtp_server or not smtp_port:
        log.warn(
            "Missing email notification configuration(s). Email notifications will not be sent."
        )

    # Load the public key into memory on startup
    with open("public_key.asc", "r") as key_file:
        key_data = key_file.read()
        PUBLIC_KEY, _ = pgpy.PGPKey.from_blob(
            key_data
        )  # Extract the key from the tuple

    def encrypt_message(message):
        encrypted_message = str(PUBLIC_KEY.encrypt(pgpy.PGPMessage.new(message)))
        return encrypted_message

    @app.before_request
    def ensure_user_token():
        if "user_token" not in session:
            session["user_token"] = generate_unique_token()

    @app.route("/")
    def index():
        owner, key_id, expires = pgp_owner_info_direct()
        return render_template(
            "index.html",
            owner_info=owner,
            key_id=key_id,
            expires=expires,
            pgp_info_available=bool(owner),
        )

    def pgp_owner_info_direct():
        owner = f"{PUBLIC_KEY.userids[0].name} <{PUBLIC_KEY.userids[0].email}>"
        key_id = f"Key ID: {str(PUBLIC_KEY.fingerprint)[-8:]}"
        if PUBLIC_KEY.expires_at is not None:
            expires = f"Exp: {PUBLIC_KEY.expires_at.strftime('%Y-%m-%d')}"
        else:
            expires = "Exp: Never"
        return owner, key_id, expires

    @app.route("/info")
    @limiter.limit("5 per minute")
    def info():
        return render_template("info.html")

    def generate_unique_token():
        return os.urandom(16).hex()

    @app.route("/send_message", methods=["POST"])
    @limiter.limit("5 per minute")
    def send_message():
        message = request.form["message"]
        encrypted_message = encrypt_message(message)
        with open("messages.txt", "a") as f:
            f.write(encrypted_message + "\n\n")
        send_email_notification(encrypted_message)

        return render_template("message-sent.html")

    def send_email_notification(message):
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = sender_email
        msg["Subject"] = "🤫 New Hush Line Message Received"

        body = f"{message}"
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, sender_email, msg.as_string())
        except Exception as e:
            log.error(f"Error sending email notification: {e}")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run()
