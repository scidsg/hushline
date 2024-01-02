from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://hushlineuser:yourpassword@localhost/hushlinedb')
db = SQLAlchemy(app)

sender_email = os.environ.get("EMAIL", None)
sender_password = os.environ.get("NOTIFY_PASSWORD", None)
smtp_server = os.environ.get("NOTIFY_SMTP_SERVER", None)
smtp_port = int(os.environ.get("NOTIFY_SMTP_PORT", 0))

if not sender_email or not sender_password or not smtp_server or not smtp_port:
    log.warn(
        "Missing email notification configuration(s). Email notifications will not be sent."
    )

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pgp_key = db.Column(db.Text, nullable=False)
    delivery_email = db.Column(db.String(120), unique=True, nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)

@app.route('/add_user', methods=['POST'])
def add_user():
    pgp_key = request.form['pgp_key']
    delivery_email = request.form['email']
    new_user = User(pgp_key=pgp_key, delivery_email=delivery_email)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"success": "User added"}), 200

@app.route("/send_message", methods=["POST"])
def send_message():
    try:
        message = request.form["message"]
        encrypted_message = encrypt_message(message)
        # Logic to associate the message with a user should be here
        new_message = Message(content=encrypted_message)  # Example usage
        db.session.add(new_message)
        db.session.commit()
        send_email_notification(encrypted_message)
        return render_template("message-sent.html")
    except Exception as e:
        log.error(f"Error in send_message: {e}")
        return jsonify({"error": "An error occurred"}), 500

def encrypt_message(message):
    encrypted_message = str(PUBLIC_KEY.encrypt(pgpy.PGPMessage.new(message)))
    return encrypted_message

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
        expires = f"Exp: Never"
    return owner, key_id, expires

@app.route("/info")
def info():
    return render_template("info.html")

@app.route("/send_message", methods=["POST"])
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

if __name__ == "__main__":
    app.run()
