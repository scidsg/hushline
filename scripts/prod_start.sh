#!/bin/bash

# Run migrations
echo "> Running migrations"
poetry run flask db upgrade

# Configure Stripe and tiers
if [ -n "$STRIPE_SECRET_KEY" ]; then
  echo "> Configuring Stripe"
  poetry run flask stripe configure
else
  echo "STRIPE_SECRET_KEY is not set. Skipping Stripe configuration."
fi

# Start the server
echo "> Starting the server"
poetry run gunicorn "hushline:create_app()" -b 0.0.0.0:8080