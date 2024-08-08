import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, session, url_for

from hushline.model import User

from .db import db


def authentication_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session:
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))

        if not session.get("is_authenticated", False):
            return redirect(url_for("verify_2fa_login"))

        return f(*args, **kwargs)

    return decorated_function


def admin_authentication_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    @authentication_required
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        user = db.session.query(User).get(session["user_id"])
        if not user or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@dataclass
class SMTPConfig:
    username: str
    server: str
    port: int
    password: str

    def validate(self) -> bool:
        return all([self.username, self.server, self.port, self.password])


def send_email(
    to_email: str, subject: str, body: str, sender_email: str, smtp_config: SMTPConfig
) -> bool:
    current_app.logger.debug(
        f"SMTP settings being used: Server: {smtp_config.server}, "
        f"Port: {smtp_config.port}, Username: {smtp_config.username}"
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
    if not smtp_config.validate():
        current_app.logger.error("SMTP server or port is not set.")
        return False

    try:
        with smtplib.SMTP(smtp_config.server, smtp_config.port) as server:
            server.starttls()
            server.login(smtp_config.username, smtp_config.password)
            server.send_message(message)
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending email: {str(e)}")
        return False
