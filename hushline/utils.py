import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Callable

from flask import current_app, flash, redirect, session, url_for

from hushline.model import User

from .db import db


def authentication_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session or not session.get("is_authenticated", False):
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function


def admin_authentication_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session or not session.get("is_authenticated", False):
            return redirect(url_for("login"))

        user = db.session.query(User).get(session["user_id"])
        if not user or not user.is_admin:
            flash("Unauthorized access.", "error")
            return redirect(url_for("index"))

        return f(*args, **kwargs)

    return decorated_function


def send_email(to_email: str, subject: str, body: str, user: User, sender_email: str) -> bool:
    current_app.logger.debug(
        f"SMTP settings being used: Server: {user.smtp_server}, "
        f"Port: {user.smtp_port}, Username: {user.smtp_username}"
    )

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = subject

    # Check if body is a bytes object
    if isinstance(body, bytes):
        # Decode the bytes object to a string
        body = body.decode("utf-8")

    message.attach(MIMEText(body, "plain"))
    if (
        user.smtp_server is None
        or user.smtp_port is None
        or user.smtp_username is None
        or user.smtp_password is None
    ):
        current_app.logger.error("SMTP server or port is not set.")
        return False

    try:
        with smtplib.SMTP(user.smtp_server, user.smtp_port) as server:
            server.starttls()
            server.login(user.smtp_username, user.smtp_password)
            server.send_message(message)
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending email: {str(e)}")
        return False
