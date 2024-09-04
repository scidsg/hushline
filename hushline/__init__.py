import logging
import os
from datetime import timedelta
from typing import Any

import stripe
from flask import Flask, flash, redirect, request, session, url_for
from flask_migrate import Migrate
from werkzeug.wrappers.response import Response

from . import admin, routes, settings
from .db import db
from .model import User
from .stripe import init_stripe
from .version import __version__


def create_app() -> Flask:
    app = Flask(__name__)

    # Configure logging
    app.logger.setLevel(logging.DEBUG)

    app.config["VERSION"] = __version__
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    # if it's a Postgres URI, replace the scheme with `postgresql+psycopg`
    # because we're using the psycopg driver
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_NAME"] = os.environ.get("SESSION_COOKIE_NAME", "__HOST-session")
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
    app.config["ONION_HOSTNAME"] = os.environ.get("ONION_HOSTNAME", None)
    app.config["IS_PERSONAL_SERVER"] = (
        os.environ.get("IS_PERSONAL_SERVER", "False").lower() == "true"
    )
    app.config["NOTIFICATIONS_ADDRESS"] = os.environ.get("NOTIFICATIONS_ADDRESS", None)
    app.config["SMTP_USERNAME"] = os.environ.get("SMTP_USERNAME", None)
    app.config["SMTP_SERVER"] = os.environ.get("SMTP_SERVER", None)
    app.config["SMTP_PORT"] = int(os.environ.get("SMTP_PORT", 0))
    app.config["SMTP_PASSWORD"] = os.environ.get("SMTP_PASSWORD", None)
    app.config["SMTP_ENCRYPTION"] = os.environ.get("SMTP_ENCRYPTION", "StartTLS")
    app.config["REQUIRE_PGP"] = os.environ.get("REQUIRE_PGP", "False").lower() == "true"
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.environ.get("STRIPE_PUBLISHABLE_KEY", None)
    app.config["STRIPE_SECRET_KEY"] = os.environ.get("STRIPE_SECRET_KEY", None)

    # Run migrations
    db.init_app(app)
    Migrate(app, db)

    # Configure Stripe
    if app.config["STRIPE_SECRET_KEY"]:
        with app.app_context():
            init_stripe(app)
    else:
        app.logger.warning("Stripe is not configured because STRIPE_SECRET_KEY is not set")

    routes.init_app(app)
    for module in [admin, settings]:
        app.register_blueprint(module.create_blueprint())

    @app.errorhandler(404)
    def page_not_found(e: Exception) -> Response:
        flash("⛓️‍💥 That page doesn't exist.", "warning")
        return redirect(url_for("index"))

    @app.context_processor
    def inject_user() -> dict[str, Any]:
        if "user_id" in session:
            user = db.session.get(User, session["user_id"])
            return {"user": user}
        return {}

    # Add Onion-Location header to all responses
    if app.config["ONION_HOSTNAME"]:

        @app.after_request
        def add_onion_location_header(response: Response) -> Response:
            response.headers["Onion-Location"] = (
                f"http://{app.config['ONION_HOSTNAME']}{request.path}"
            )
            return response

    return app
