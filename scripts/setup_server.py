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
        pgp_key_address = request.form.get('pgp_key_address')

        # Save the configuration
        with open('/tmp/setup_config.json', 'w') as f:
            json.dump({
                'email': email,
                'smtp_server': smtp_server,
                'password': password,
                'smtp_port': smtp_port,
                'pgp_key_address': pgp_key_address
            }, f)

        setup_complete = True

        return redirect(url_for('index'))

    return render_template('setup.html')

@app.route('/')
def index():
    if not setup_complete:
        return redirect(url_for('setup'))
    
    return 'Setup complete! The installation script will now resume.'

def get_local_ip():
    local_ip = ''
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # use an external facing address
        s.connect(("hushline.app", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception as e:
        print(f"Could not obtain local IP: {e}")
        local_ip = "127.0.0.1"

    return local_ip

if __name__ == '__main__':
    local_ip = get_local_ip()
    qr = segno.make(f'http://{local_ip}:5000/setup')
    with open("/tmp/qr_code.txt", "w") as f:
        qr.terminal(out=f)
    app.run(host='0.0.0.0', port=5000)
