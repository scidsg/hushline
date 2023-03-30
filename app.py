from flask import Flask, render_template, request, jsonify
from flask_mail import Mail, Message
import os
import pgpy

app = Flask(__name__)

# Configure Flask-Mail
app.config['MAIL_SERVER'] = os.environ['SMTP_SERVER']
app.config['MAIL_PORT'] = int(os.environ['SMTP_PORT'])
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ['EMAIL']
app.config['MAIL_PASSWORD'] = os.environ['SMTP_PASSWORD']

mail = Mail(app)

def send_email(subject, body):
    msg = Message(subject,
                  sender=os.environ['EMAIL'],
                  recipients=[os.environ['EMAIL']])
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
