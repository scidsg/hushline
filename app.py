from flask import Flask, render_template, request, jsonify
from flask_mail import Mail, Message
import os
import pgpy
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

app = Flask(__name__)

# Configure Flask-Mail
app.config['MAIL_SERVER'] = os.environ['MAIL_SERVER']
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.environ['MAIL_USERNAME']
app.config['MAIL_PASSWORD'] = os.environ['MAIL_PASSWORD_HASHED']
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)

def decrypt_password(encrypted_password, secret_key):
    secret_key = bytes.fromhex(secret_key)  # Add this line to convert the secret_key to bytes
    cipher = AES.new(secret_key, AES.MODE_ECB)
    decrypted_password = cipher.decrypt(base64.b64decode(encrypted_password))
    return decrypted_password.decode("utf-8").strip()

def encrypt_message(message, public_key_path):
    with open(public_key_path, 'r') as key_file:
        key_data = key_file.read()
    public_key, _ = pgpy.PGPKey.from_blob(key_data)  # Extract the key from the tuple
    encrypted_message = str(public_key.encrypt(pgpy.PGPMessage.new(message)))
    return encrypted_message

def send_email(encrypted_message):
    decrypted_password = decrypt_password(os.environ['MAIL_PASSWORD_HASHED'], os.environ['SECRET_KEY'])
    mail = Mail(app)
    mail.server.password = decrypted_password
    msg = Message("New Encrypted Message", sender=app.config['MAIL_USERNAME'], recipients=[os.environ['EMAIL']])
    msg.body = "You have received a new encrypted message:\n\n" + encrypted_message
    mail.send(msg)
    
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save_message', methods=['POST'])
def save_message():
    message = request.form['message']
    encrypted_message = encrypt_message(message, 'public_key.asc')
    with open('messages.txt', 'a') as f:
        f.write(encrypted_message + '\n\n')
    send_email(encrypted_message)
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
