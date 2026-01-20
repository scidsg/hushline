import logging
from typing import Any, Mapping, Optional, Tuple, Union

from flask import Flask, render_template, request, session, url_for
from jinja2 import StrictUndefined
from werkzeug.exceptions import HTTPException, InternalServerError
from werkzeug.wrappers.response import Response

from hushline import admin, premium, routes, settings, storage
from hushline.cli_reg import register_reg_commands
from hushline.cli_stripe import register_stripe_commands
from hushline.config import AliasMode, load_config
from hushline.db import db, migrate
from hushline.md import md_to_html
from hushline.model import OrganizationSetting, User
from hushline.secure_session import EncryptedSessionInterface
from hushline.storage import public_store
from hushline.version import __version__


def create_app(config: Optional[Mapping[str, Any]] = None) -> Flask:
    app = Flask(__name__)
    app.session_interface = EncryptedSessionInterface()

    if app.config["DEBUG"] or app.config["TESTING"]:
        app.logger.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(format="%(levelname)s:%(message)s")

    if not config:
        config = load_config()

    # hushline specific configs

    app.config.from_mapping(config)
    configure_jinja(app)
    db.init_app(app)
    migrate.init_app(app, db)
    public_store.init_app(app)

    routes.init_app(app)
    for module in [admin, settings, storage]:
        app.register_blueprint(module.create_blueprint())

    if app.config.get("STRIPE_SECRET_KEY"):
        app.register_blueprint(premium.create_blueprint(app))
        # Initialize Stripe
        with app.app_context():
            premium.init_stripe()

    # Add Content-Security-Policy header to all responses
    @app.after_request
    def add_security_header(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = ";".join(
            f"{k} {v}"
            for (k, v) in {
                "default-src": "'self'",
                "style-src": "'self' 'unsafe-inline'",
                "script-src": " ".join(
                    [
                        "'self'",
                        "https://js.stripe.com",
                        "https://cdn.jsdelivr.net",
                        "'wasm-unsafe-eval'",
                        "'unsafe-eval'",
                    ]
                ),
                "script-src-elem": "'self' 'unsafe-inline'",
                "img-src": "'self' data: https:",
                "media-src": "'self' data:",
                "worker-src": "'self' blob:",
                "frame-ancestors": "'none'",
                "connect-src": "'self' https://api.stripe.com https://cdn.jsdelivr.net data:",
                "child-src": "https://js.stripe.com",
                "frame-src": "https://js.stripe.com",
            }.items()
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=();"  # noqa: E501
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # If SERVER_NAME does not end in .onion, add Strict-Transport-Security
        if not (app.config.get("SERVER_NAME") or "").endswith(".onion"):
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubdomains"

        return response

    # Add Onion-Location header to all responses
    if onion := app.config.get("ONION_HOSTNAME"):

        @app.after_request
        def add_onion_location_header(response: Response) -> Response:
            response.headers["Onion-Location"] = f"http://{onion}{request.path}"
            return response

    register_error_handlers(app)

    # Register custom CLI commands
    register_reg_commands(app)
    register_stripe_commands(app)

    return app


def configure_jinja(app: Flask) -> None:
    app.jinja_env.globals["hushline_version"] = __version__
    app.jinja_env.globals["AliasMode"] = AliasMode

    app.jinja_env.filters["markdown"] = md_to_html

    if app.config.get("FLASK_ENV") == "development":
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
        data = OrganizationSetting.fetch(
            OrganizationSetting.BRAND_NAME,
            OrganizationSetting.BRAND_PRIMARY_COLOR,
            OrganizationSetting.GUIDANCE_ENABLED,
            OrganizationSetting.GUIDANCE_EXIT_BUTTON_TEXT,
            OrganizationSetting.GUIDANCE_EXIT_BUTTON_LINK,
            OrganizationSetting.GUIDANCE_PROMPTS,
            OrganizationSetting.HIDE_DONATE_BUTTON,
            OrganizationSetting.REGISTRATION_ENABLED,
            OrganizationSetting.REGISTRATION_CODES_REQUIRED,
        )

        data.update(
            alias_mode=app.config["ALIAS_MODE"],
            fields_mode=app.config["FIELDS_MODE"],
            directory_verified_tab_enabled=app.config["DIRECTORY_VERIFIED_TAB_ENABLED"],
            is_onion_service=request.host.lower().endswith(".onion"),
            is_premium_enabled=bool(app.config.get("STRIPE_SECRET_KEY", False)),
            registration_settings_enabled=app.config["REGISTRATION_SETTINGS_ENABLED"],
            registration_enabled=data.get(OrganizationSetting.REGISTRATION_ENABLED, False),
            registration_codes_required=data.get(
                OrganizationSetting.REGISTRATION_CODES_REQUIRED, False
            ),
            setup_incomplete=False,
        )

        if "user_id" in session:
            user = db.session.get(User, session["user_id"])
            data["user"] = user
            if user:
                username = user.primary_username
                data["setup_incomplete"] = bool(
                    not username
                    or not (username.display_name or "").strip()
                    or not (username.bio or "").strip()
                    or not user.pgp_key
                    or not user.enable_email_notifications
                    or not user.email_include_message_content
                    or not user.email_encrypt_entire_body
                    or not user.email
                )

        return data

    @app.context_processor
    def inject_logo() -> dict[str, str | None]:
        val = None
        if setting := OrganizationSetting.fetch_one(OrganizationSetting.BRAND_LOGO):
            val = url_for("storage.public", path=setting)
        return {"brand_logo_url": val}


def register_error_handlers(app: Flask) -> None:
    # don't register these in development. we want pretty error messages in the browser
    if app.config["DEBUG"] and not app.config["TESTING"]:
        return

    @app.errorhandler(Exception)
    def handle_generic_exception(e: Exception) -> Union[HTTPException, Tuple[str, int]]:
        if isinstance(e, HTTPException):
            return e

        app.logger.info(f"Unhandled error: {e}", exc_info=True)

        http_e = InternalServerError()
        return render_template(
            "error.html",
            title=http_e.name,
            status_code=http_e.code,
            description=http_e.description,
        ), http_e.code

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException) -> Tuple[str, int]:
        return render_template(
            "error.html",
            title=e.name,
            status_code=e.code,
            description=e.description,
        ), (e.code or 500)
