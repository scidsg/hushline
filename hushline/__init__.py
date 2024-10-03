import asyncio
import logging
import os
from datetime import timedelta
from typing import Any

from flask import Flask, flash, redirect, request, session, url_for
from flask.cli import AppGroup
from flask_migrate import Migrate
from jinja2 import StrictUndefined
from sqlalchemy.exc import ProgrammingError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers.response import Response

from . import admin, premium, routes, settings
from .db import db
from .model import HostOrganization, Tier, User
from .version import __version__


def create_app() -> Flask:
    app = Flask(__name__)

    # Configure logging
    app.logger.setLevel(logging.DEBUG)

    # sqlalchemy configs
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    # if it's a Postgres URI, replace the scheme with `postgresql+psycopg`
    # because we're using the psycopg driver
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # cookie configs
    app.config["FLASK_ENV"] = os.environ.get("FLASK_ENV")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["SESSION_COOKIE_NAME"] = os.environ.get("SESSION_COOKIE_NAME", "__HOST-session")
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    # hushline specific configs
    app.config["VERSION"] = __version__
    app.config["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")
    app.config["ONION_HOSTNAME"] = os.environ.get("ONION_HOSTNAME", None)
    app.config["IS_PERSONAL_SERVER"] = (
        os.environ.get("IS_PERSONAL_SERVER", "False").lower() == "true"
    )
    app.config["REGISTRATION_CODES_REQUIRED"] = (
        os.environ.get("REGISTRATION_CODES_REQUIRED", "true").lower() == "true"
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
    app.config["STRIPE_WEBHOOK_SECRET"] = os.environ.get("STRIPE_WEBHOOK_SECRET", None)

    # Handle the tips domain for profile verification
    app.config["SERVER_NAME"] = os.getenv("SERVER_NAME")
    app.config["PREFERRED_URL_SCHEME"] = "https" if os.getenv("SERVER_NAME") is not None else "http"

    if not app.config["IS_PERSONAL_SERVER"]:
        # if were running the managed service, we are behind a proxy
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=2, x_proto=1, x_host=0, x_port=0, x_prefix=0
        )

    # jinja configs
    if app.config.get("FLASK_ENV", None) == "development":
        app.logger.info("Development environment detected, enabling jinja2.StrictUndefined")
        app.jinja_env.undefined = StrictUndefined

    # Run migrations
    db.init_app(app)
    Migrate(app, db)

    # Initialize Stripe
    if app.config["STRIPE_SECRET_KEY"]:
        with app.app_context():
            premium.init_stripe()

    routes.init_app(app)
    for module in [admin, settings]:
        app.register_blueprint(module.create_blueprint())

    if app.config["STRIPE_SECRET_KEY"]:
        app.register_blueprint(premium.create_blueprint(app))

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

    @app.context_processor
    def inject_host() -> dict[str, HostOrganization]:
        return dict(host_org=HostOrganization.fetch_or_default())

    @app.context_processor
    def inject_is_personal_server() -> dict[str, Any]:
        return {"is_personal_server": app.config["IS_PERSONAL_SERVER"]}

    @app.context_processor
    def inject_is_premium_enabled() -> dict[str, Any]:
        return {"is_premium_enabled": bool(app.config.get("STRIPE_SECRET_KEY", False))}

    # Add Onion-Location header to all responses
    if app.config["ONION_HOSTNAME"]:

        @app.after_request
        def add_onion_location_header(response: Response) -> Response:
            response.headers["Onion-Location"] = (
                f"http://{app.config['ONION_HOSTNAME']}{request.path}"
            )
            return response

    # Register custom CLI commands
    register_commands(app)

    # we can't
    if app.config.get("FLASK_ENV", None) != "development":
        with app.app_context():
            try:
                host_org = HostOrganization.fetch()
            except ProgrammingError:
                app.logger.warning(
                    "Could not check for existence of HostOrganization", exc_info=True
                )
            else:
                if host_org is None:
                    app.logger.warning("HostOrganization data not found in database.")

    return app


def register_commands(app: Flask) -> None:
    stripe_cli = AppGroup("stripe")

    @stripe_cli.command("configure")
    def configure() -> None:
        """Configure Stripe and premium tiers"""
        # Make sure tiers exist
        with app.app_context():
            free_tier = Tier.free_tier()
            if not free_tier:
                free_tier = Tier(name="Free", monthly_amount=0)
                db.session.add(free_tier)
                db.session.commit()
            business_tier = Tier.business_tier()
            if not business_tier:
                business_tier = Tier(name="Business", monthly_amount=2000)
                db.session.add(business_tier)
                db.session.commit()

        # Configure Stripe
        if app.config["STRIPE_SECRET_KEY"]:
            with app.app_context():
                premium.init_stripe()
                premium.create_products_and_prices()
        else:
            app.logger.info("Skipping Stripe configuration because STRIPE_SECRET_KEY is not set")

    @stripe_cli.command("start-worker")
    def start_worker() -> None:
        """Start the Stripe worker"""
        if not app.config["STRIPE_SECRET_KEY"]:
            app.logger.error("Cannot start the Stripe worker without a STRIPE_SECRET_KEY")
            return

        with app.app_context():
            asyncio.run(premium.worker(app))

    app.cli.add_command(stripe_cli)
