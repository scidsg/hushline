#!/bin/bash

# Run migrations
poetry run flask db upgrade

# Start the server
poetry run gunicorn "hushline:create_app()" -b 0.0.0.0:8080
