import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from flask import current_app, flash, redirect, session, url_for

from hushline.model import User


def require_2fa(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or not session.get("is_authenticated", False):
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))
        if session.get("2fa_required", False) and not session.get("2fa_verified", False):
            flash("👉 2FA verification required.")
            return redirect(url_for("verify_2fa_login"))
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
    try:
        with smtplib.SMTP(user.smtp_server, user.smtp_port) as server:
            server.starttls()
            server.login(user.smtp_username, user.smtp_password)
            server.send_message(message)
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending email: {str(e)}")
        return False
