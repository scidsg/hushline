#!/bin/bash

# Run migrations
poetry run make migrate

# Start the server
poetry run flask run -p 8080 --host 0.0.0.0
