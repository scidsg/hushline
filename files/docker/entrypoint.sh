#!/bin/sh
# Stop on any error
set -e
export PYTHONPATH=/src:$PYTHONPATH

echo "Running Flask Migrations"
# Ensure the environment is properly set
export FLASK_APP="hushline:create_app"
flask db upgrade || echo "Upgrade failed"

echo "Starting Gunicorn"
exec gunicorn "hushline:create_app()" --bind "0.0.0.0:8080" --workers 2 --capture-output --access-logformat "%(r)s %(s)s" --forwarded-allow-ips "0.0.0.0"
