from dotenv import load_dotenv

load_dotenv("/etc/hushline/hushline.conf")

import logging  # noqa: E402
import os  # noqa: E402
from datetime import timedelta  # noqa: E402
from typing import Any, Tuple  # noqa: E402

from flask import Flask, Response, flash, redirect, render_template, session, url_for  # noqa: E402
from flask_limiter import RateLimitExceeded  # noqa: E402
from flask_migrate import Migrate  # noqa: E402
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from . import admin, routes, settings  # noqa: E402
from .db import db  # noqa: E402
from .ext import limiter  # noqa: E402
from .model import User  # noqa: E402


def create_app() -> Flask:
    app = Flask(__name__)

    config_path = "/etc/hushline/hushline.conf"
    load_dotenv(config_path)
    app.logger.debug(f"Loaded ENCRYPTION_KEY: {os.environ.get('ENCRYPTION_KEY')}")

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(e):
        return render_template("rate_limit_exceeded.html"), 429

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)  # type: ignore

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_NAME"] = "__Host-session"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    # Conditional SSL configuration based on environment
    if os.getenv("FLASK_ENV") == "production":
        ssl_cert = os.getenv("SSL_CERT_PATH")
        ssl_key = os.getenv("SSL_KEY_PATH")

        # Ensure SSL files exist
        if not all(os.path.exists(path) for path in [ssl_cert, ssl_key] if path):
            raise FileNotFoundError("SSL certificate or key file is missing.")

    db.init_app(app)
    _ = Migrate(app, db)
    limiter.init_app(app)

    app.logger.setLevel(logging.DEBUG)

    routes.init_app(app)
    for module in [admin, settings]:
        app.register_blueprint(module.create_blueprint())

    @app.errorhandler(404)
    def page_not_found(e) -> Response:
        flash("⛓️‍💥 That page doesn't exist.", "warning")
        return redirect(url_for("index"))

    @app.context_processor
    def inject_user() -> dict[str, Any]:
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            return {"user": user}
        return {}

    @app.errorhandler(Exception)
    def handle_exception(e) -> Tuple[str, int]:
        # Consider adjusting error handling as per your logging preferences
        app.logger.error(
            f"Error: {e}", exc_info=True
        )  # Ensure appropriate logging configuration is in place
        return "An internal server error occurred", 500

    @app.cli.group(
        help="More DB management besides migration",
    )
    def db_extras() -> None:
        pass

    @db_extras.command(help="Initialize the dev DB")
    def init_db() -> None:
        db.create_all()

    return app
