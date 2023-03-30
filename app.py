from flask import Flask, render_template, request, jsonify
import os
import pgpy
import configparser
import smtplib
from email.message import EmailMessage

app = Flask(__name__)

# Read the configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Use the config values for email settings
SENDER_EMAIL = config.get('EMAIL', 'SenderEmail')
SENDER_PASSWORD = config.get('EMAIL', 'SenderPassword')
RECIPIENT_EMAIL = config.get('EMAIL', 'RecipientEmail')
SMTP_SERVER = config.get('EMAIL', 'SMTPServer')

def send_email_notification(subject, body):
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = "New Hush Line Message"
    msg['From'] = "notifications@hushline.app"
    msg['To'] = EMAIL

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

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
    # Send the email notification
    send_email_notification('New Hush Line Message', 'A new encrypted message has been submitted.')

    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
