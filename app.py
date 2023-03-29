from flask import Flask, render_template, request, jsonify
import os
import pgpy

app = Flask(__name__)

def encrypt_message(message, public_key_path):
    with open(public_key_path, 'r') as key_file:
        key_data = key_file.read()
    public_key, _ = pgpy.PGPKey.from_blob(key_data)  # Extract the key from the tuple
    encrypted_message = str(public_key.encrypt(pgpy.PGPMessage.new(message)))
    return encrypted_message

@app.route('/')
def index():
    return render_template('index.html')

def save_message():  
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
