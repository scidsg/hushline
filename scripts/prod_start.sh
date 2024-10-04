#!/bin/bash

# Run migrations
poetry run flask db upgrade

# Configure Stripe and tiers
poetry run flask stripe configure

# Start the server
poetry run gunicorn "hushline:create_app()" -b 0.0.0.0:8080