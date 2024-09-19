#!/bin/bash

# Run migrations
poetry run flask db upgrade

# Make sure initial objects are created in Stripe
flask stripe create-products-and-prices

# Start the server
poetry run gunicorn "hushline:create_app()" -b 0.0.0.0:8080