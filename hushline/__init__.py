import logging
import os
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, session, url_for
from flask_limiter import RateLimitExceeded
from flask_migrate import Migrate
from flask.cli import AppGroup
from werkzeug.middleware.proxy_fix import ProxyFix

from . import admin, routes, settings
from .db import db
from .ext import bcrypt, limiter
from .model import User
from .crypto import list_keys

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(e):
        return render_template("rate_limit_exceeded.html"), 429

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["SQLALCHEMY_DATABASE_URI"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SESSION_COOKIE_NAME"] = "__Host-session"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    db.init_app(app)
    _ = Migrate(app, db)
    limiter.init_app(app)
    bcrypt.init_app(app)

    file_handler = RotatingFileHandler("flask.log", maxBytes=1024 * 1024 * 100, backupCount=20)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]")
    )
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.DEBUG)

    routes.init_app(app)
    for module in [admin, settings]:
        app.register_blueprint(module.create_blueprint())

    @app.cli.group(help="Debugging related commands")
    def debug() -> None:
        pass

    @debug.command("list-gpg-keys")
    def debug_list_gpg_keys():
        """List GPG keys for debugging."""
        if os.getenv("HUSHLINE_DEBUG_OPTS") == "1":
            list_keys()
        else:
            print("Debugging options are not enabled. Set HUSHLINE_DEBUG_OPTS=1 to enable.")

    app.cli.add_command(debug)

    @app.errorhandler(404)
    def page_not_found(e):
        flash("⛓️‍💥 That page doesn't exist.", "warning")
        return redirect(url_for("index"))

    @app.context_processor
    def inject_user():
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            return {"user": user}
        return {}

    @app.errorhandler(Exception)
    def handle_exception(e):
        # Log the error and stacktrace
        app.logger.error(f"Error: {e}", exc_info=True)
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
