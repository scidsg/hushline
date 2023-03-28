# Anonymous Tip Line

## Easy Install

```
curl -sSL https://raw.githubusercontent.com/scidsg/hush-line/master/install.sh | bash
```

To deploy your Flask application to a production environment, you can follow these general steps:

    Use a production-ready WSGI server like Gunicorn to run your Flask app.
    Configure a reverse proxy like Nginx to handle incoming requests and forward them to your Flask app.
    Secure your application with an SSL certificate using Let's Encrypt.
    (Optional) Deploy your application to a cloud service like AWS, Google Cloud, or Heroku.

Here's a step-by-step guide to deploy your Flask application using Gunicorn, Nginx, and Let's Encrypt on an Ubuntu server:

## Step 1: Install necessary packages

Install Gunicorn and Nginx:

```
sudo apt update
sudo apt install gunicorn nginx
```

## Step 2: Run your Flask app with Gunicorn

Navigate to your Flask app directory and run the following command to start your Flask app with Gunicorn:

bash

gunicorn --bind 0.0.0.0:8000 app:app

This command will start Gunicorn on port 8000.

## Step 3: Configure Nginx

Create a new Nginx configuration file for your Flask app:

```
sudo nano /etc/nginx/sites-available/my_flask_app
```

Add the following configuration to the file, replacing your_domain with your actual domain:

```
server {
    listen 80;
    server_name your_domain;

    location / {
        proxy_pass http://0.0.0.0:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Save and exit the file.

Create a symbolic link for the configuration file:

```
sudo ln -s /etc/nginx/sites-available/my_flask_app /etc/nginx/sites-enabled/
```

Test the Nginx configuration:

```
sudo nginx -t
```

If the test is successful, restart Nginx:

```
sudo systemctl restart nginx
```

## Step 4: Secure your application with Let's Encrypt

Install Certbot and the Nginx plugin:

```
sudo apt install certbot python3-certbot-nginx
```

Obtain and install the SSL certificate:

```
sudo certbot --nginx -d your_domain
```

Follow the prompts to complete the certificate installation. Certbot will automatically modify your Nginx configuration to use the SSL certificate.

## Step 5: (Optional) Deploy your application to a cloud service

If you prefer to deploy your Flask application to a cloud service like AWS, Google Cloud, or Heroku, you can follow their respective documentation and guidelines:

    Deploying a Flask app on AWS Elastic Beanstalk
    Deploying a Flask app on Google App Engine
    Deploying a Flask app on Heroku

Remember to set your Flask app's environment to production and disable debug mode before deploying. In your app.py, change the last line to:

```
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
```

And in your application's environment, set the FLASK_ENV variable to production:

```
export FLASK_ENV=production
```

This will ensure your application is running in a production environment.
