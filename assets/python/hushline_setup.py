from flask import Flask, request, render_template, redirect, url_for
import json
import os
import segno
import requests
import socket

app = Flask(__name__)

# Flag to indicate whether setup is complete
setup_complete = os.path.exists('/tmp/setup_config.json')

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    global setup_complete
    if setup_complete:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        smtp_server = request.form.get('smtp_server')
        password = request.form.get('password')
        smtp_port = request.form.get('smtp_port')
        pgp_public_key = request.form.get('pgp_public_key')

        # Save the configuration
        with open('/tmp/setup_config.json', 'w') as f:
            json.dump({
                'email': email,
                'smtp_server': smtp_server,
                'password': password,
                'smtp_port': smtp_port,
                'pgp_public_key': pgp_public_key
            }, f)

        setup_complete = True

        # Save the provided PGP key to a file
        with open('/home/hush/hushline/public_key.asc', 'w') as keyfile:
            keyfile.write(pgp_public_key)

        return redirect(url_for('index'))

    return render_template('setup.html')

@app.route('/')
def index():
    if not setup_complete:
        return redirect(url_for('setup'))
    
    return '👍 Successfully submitted! The installation script will now resume.'

if __name__ == '__main__':
    qr = segno.make(f'https://hushline.local/setup')
    with open("/tmp/qr_code.txt", "w") as f:
        qr.terminal(out=f)
    app.run(host='0.0.0.0', port=5001)