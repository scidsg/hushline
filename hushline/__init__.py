import logging
import os
from datetime import timedelta
from typing import Any

from flask import Flask, flash, redirect, render_template, session, url_for
from flask_limiter import RateLimitExceeded
from flask_migrate import Migrate
from werkzeug.wrappers.response import Response

from . import admin, routes, settings
from .db import db
from .limiter import limiter
from .model import User


def create_app() -> Flask:
    print("Creating app")
    app = Flask(__name__)

    # Configure logging
    app.logger.setLevel(logging.DEBUG)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_NAME"] = "__Host-session"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    # Run migrations
    print("Running migrations")
    db.init_app(app)
    Migrate(app, db)

    limiter.init_app(app)

    routes.init_app(app)
    for module in [admin, settings]:
        app.register_blueprint(module.create_blueprint())

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(e: RateLimitExceeded) -> tuple[str, int]:
        return render_template("rate_limit_exceeded.html"), 429

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

    print("App created")
    return app
