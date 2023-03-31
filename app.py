from flask import Flask, render_template, request, jsonify
from flask_mail import Mail, Message
import os
import pgpy
import configparser

app = Flask(__name__)

# Load email configuration from config.ini
config = configparser.ConfigParser()
config.read('config.ini')

smtp_server = config.get('EMAIL', 'SMTPServer')
sender_password = config.get('EMAIL', 'SenderPassword')
email = config.get('EMAIL', 'RecipientEmail')

# Configure Flask-Mail
app.config.update(
    MAIL_SERVER=smtp_server,
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="notifications@hushline.app",
    MAIL_PASSWORD=sender_password,
    MAIL_DEFAULT_SENDER="notifications@hushline.app",
    MAIL_RECIPIENT=email
)

mail = Mail(app)

def send_email(subject, body):
    msg = Message(subject,
                  sender=email,
                  recipients=[email])
    msg.body = body
    mail.send(msg)

def encrypt_message(message, public_key_path):
    with open(public_key_path, 'r') as key_file:
        key_data = key_file.read()
    public_key, _ = pgpy.PGPKey.from_blob(key_data)  # Extract the key from the tuple
    encrypted_message = str(public_key.encrypt(pgpy.PGPMessage.new(message)))
    return encrypted_message

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save_message', methods=['POST'])
def save_message():
    message = request.form['message']
    encrypted_message = encrypt_message(message, 'public_key.asc')
    with open('messages.txt', 'a') as f:
        f.write(encrypted_message + '\n\n')
    send_email('New encrypted message received', encrypted_message)
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
