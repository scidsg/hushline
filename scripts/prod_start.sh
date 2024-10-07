#!/bin/bash

# Run migrations
echo "> Running migrations"
poetry run flask db upgrade

# Configure Stripe and tiers
echo "> Configuring Stripe"
poetry run flask stripe configure

# Start the server
echo "> Starting the server"
poetry run gunicorn "hushline:create_app()" -b 0.0.0.0:8080