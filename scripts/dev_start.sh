#!/bin/bash

# Configure Stripe and tiers
flask stripe configure

# Start the server
poetry run flask run --debug --host=0.0.0.0 --port=8080 --with-threads