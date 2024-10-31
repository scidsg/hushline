import asyncio
import logging
from typing import Any, Mapping, Optional

from flask import Flask, flash, redirect, request, session, url_for
from flask.cli import AppGroup
from jinja2 import StrictUndefined
from werkzeug.wrappers.response import Response

from . import admin, premium, routes, settings, storage
from .config import AliasMode, load_config
from .db import db, migrate
from .model import HostOrganization, Tier, User
from .version import __version__


def create_app(config: Optional[Mapping[str, Any]] = None) -> Flask:
    app = Flask(__name__)
    app.logger.setLevel(logging.DEBUG)

    if not config:
        config = load_config()

    # hushline specific configs

    app.config.from_mapping(config)
    configure_jinja(app)

    db.init_app(app)
    migrate.init_app(app, db)

    routes.init_app(app)
    for module in [admin, settings]:
        app.register_blueprint(module.create_blueprint())

    if app.config.get("STRIPE_SECRET_KEY"):
        app.register_blueprint(premium.create_blueprint(app))
        # Initialize Stripe
        with app.app_context():
            premium.init_stripe()

    storage.init_app(app)

    @app.errorhandler(404)
    def page_not_found(e: Exception) -> Response:
        flash("⛓️‍💥 That page doesn't exist.", "warning")
        return redirect(url_for("index"))

    # Add Onion-Location header to all responses
    if onion := app.config.get("ONION_HOSTNAME"):

        @app.after_request
        def add_onion_location_header(response: Response) -> Response:
            response.headers["Onion-Location"] = f"http://{onion}{request.path}"
            return response

    # Register custom CLI commands
    register_commands(app)

    return app


def configure_jinja(app: Flask) -> None:
    app.jinja_env.globals["hushline_version"] = __version__
    app.jinja_env.globals["AliasMode"] = AliasMode

    if app.config.get("FLASK_ENV") == "development":
        app.logger.info("Development environment detected, enabling jinja2.StrictUndefined")
        app.jinja_env.undefined = StrictUndefined

    # always pop the config to avoid accidentally dumping all our secrets to the user
    app.jinja_env.globals.pop("config", None)
    app.jinja_env.globals["smtp_forwarding_message_html"] = app.config[
        "SMTP_FORWARDING_MESSAGE_HTML"
    ]
    if onion_hostname := app.config.get("ONION_HOSTNAME"):
        app.jinja_env.globals["onion_hostname"] = onion_hostname

    @app.context_processor
    def inject_variables() -> dict[str, Any]:
        data = {
            "alias_mode": app.config["ALIAS_MODE"],
            "directory_verified_tab_enabled": app.config["DIRECTORY_VERIFIED_TAB_ENABLED"],
            "host_org": HostOrganization.fetch_or_default(),
            "is_onion_service": request.host.lower().endswith(".onion"),
            "is_premium_enabled": bool(app.config.get("STRIPE_SECRET_KEY", False)),
            "file_uploads_enabled": app.config["FILE_UPLOADS_ENABLED"],
        }
        if "user_id" in session:
            data["user"] = db.session.get(User, session["user_id"])
        return data


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
