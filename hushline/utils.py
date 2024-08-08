import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Callable

from flask import current_app, flash, redirect, session, url_for


def require_2fa(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session or not session.get("is_authenticated", False):
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))
        if session.get("2fa_required", False) and not session.get("2fa_verified", False):
            flash("👉 2FA verification required.")
            return redirect(url_for("verify_2fa_login"))
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
