import logging
import math
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

    def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
        hex_value = hex_color.lstrip("#")
        r = int(hex_value[0:2], 16) / 255
        g = int(hex_value[2:4], 16) / 255
        b = int(hex_value[4:6], 16) / 255
        return r, g, b

    SRGB_TO_LINEAR_THRESHOLD = 0.04045
    LINEAR_TO_SRGB_THRESHOLD = 0.0031308

    def _srgb_to_linear(value: float) -> float:
        return (
            value / 12.92 if value <= SRGB_TO_LINEAR_THRESHOLD else ((value + 0.055) / 1.055) ** 2.4
        )

    def _linear_to_srgb(value: float) -> float:
        return (
            12.92 * value
            if value <= LINEAR_TO_SRGB_THRESHOLD
            else 1.055 * (value ** (1 / 2.4)) - 0.055
        )

    def _brand_dark_color(hex_color: str) -> str:
        r, g, b = _hex_to_rgb(hex_color)
        r_lin = _srgb_to_linear(r)
        g_lin = _srgb_to_linear(g)
        b_lin = _srgb_to_linear(b)

        l_val = 0.4122214708 * r_lin + 0.5363325363 * g_lin + 0.0514459929 * b_lin
        m_val = 0.2119034982 * r_lin + 0.6806995451 * g_lin + 0.1073969566 * b_lin
        s_val = 0.0883024619 * r_lin + 0.2817188376 * g_lin + 0.6299787005 * b_lin

        l_ = l_val ** (1 / 3)
        m_ = m_val ** (1 / 3)
        s_ = s_val ** (1 / 3)

        lab_l = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
        lab_a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
        lab_b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

        c = (lab_a**2 + lab_b**2) ** 0.5
        h = math.degrees(math.atan2(lab_b, lab_a))

        l_clamped = min(0.98, max(0.96, lab_l + 0.425))
        c_scaled = 0.5 * c

        h_rad = math.radians(h)
        o_a = c_scaled * math.cos(h_rad)
        o_b = c_scaled * math.sin(h_rad)

        l_ = l_clamped + 0.3963377774 * o_a + 0.2158037573 * o_b
        m_ = l_clamped - 0.1055613458 * o_a - 0.0638541728 * o_b
        s_ = l_clamped - 0.0894841775 * o_a - 1.291485548 * o_b

        l3 = l_ * l_ * l_
        m3 = m_ * m_ * m_
        s3 = s_ * s_ * s_

        r_lin = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
        g_lin = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
        b_lin = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3

        r = max(0, min(1, _linear_to_srgb(r_lin)))
        g = max(0, min(1, _linear_to_srgb(g_lin)))
        b = max(0, min(1, _linear_to_srgb(b_lin)))

        return f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"

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
            user=None,
        )
        brand_primary_color = data.get(OrganizationSetting.BRAND_PRIMARY_COLOR, "#7d25c1")
        data["brand_primary_color_dark"] = _brand_dark_color(brand_primary_color)

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
                    or not username.show_in_directory
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
