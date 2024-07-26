import getpass
import logging
import os
import warnings
from base64 import urlsafe_b64decode
from datetime import timedelta
from secrets import token_bytes
from typing import Any

from flask import Flask, flash, redirect, request, session, url_for
from flask_migrate import Migrate
from werkzeug.wrappers.response import Response

from . import admin, routes, settings
from .crypto import SecretsManager
from .db import db
from .model import InfrastructureAdmin, User


def _summon_db_secret(*, name: str, length: int = 32) -> bytearray:
    if (entry := InfrastructureAdmin.query.get(name)) is None:
        secret = bytearray(token_bytes(length))
        db.session.add(InfrastructureAdmin(name=name, value=secret))
        db.session.commit()
    else:
        secret = entry.value
        if len(secret) != length:
            warnings.warn("The secret's length doesn't match its declaration.", stacklevel=2)

    return secret


def _interactive_encryption_seed(app: Flask) -> None:
    app.config["VAULT"] = SecretsManager(
        admin_secret=bytearray(getpass.getpass("admin secret: "), encoding="utf-8"),
        salt=_summon_db_secret(name=InfrastructureAdmin._APP_ADMIN_SECRET_SALT_NAME),
    )


def _environment_encryption_seed(app: Flask) -> None:
    admin_secret = bytearray(urlsafe_b64decode(os.environ.get("ADMIN_SECRET", "")))
    if not admin_secret:
        raise ValueError("Admin secret not found. Please check your .env file.")

    app.config["VAULT"] = SecretsManager(
        admin_secret=admin_secret,
        salt=_summon_db_secret(name=InfrastructureAdmin._APP_ADMIN_SECRET_SALT_NAME),
    )


def create_app() -> Flask:
    app = Flask(__name__)

    # Configure logging
    app.logger.setLevel(logging.DEBUG)

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

    # Run migrations
    db.init_app(app)
    Migrate(app, db)

    with app.app_context():
        db.create_all()

        match os.environ.get("ADMIN_INPUT_SOURCE", "environment").strip().lower():
            case "interactive":
                _interactive_encryption_seed(app)
            case "environment":
                _environment_encryption_seed(app)
            case ADMIN_INPUT_SOURCE:
                raise ValueError(f"{ADMIN_INPUT_SOURCE=} is an unsupported input source.")

        app.config["SECRET_KEY"] = _summon_db_secret(
            name=InfrastructureAdmin._FLASK_COOKIE_SECRET_KEY_NAME
        ).hex()

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
            user = User.query.get(session["user_id"])
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
