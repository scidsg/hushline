#!/bin/bash

# Configure Stripe and tiers
poetry run flask stripe configure

# Start the server
poetry run flask run --debug --host=0.0.0.0 --port=8080 --with-threads