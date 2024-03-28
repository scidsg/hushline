import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from flask import current_app, flash, redirect, session, url_for

from hushline.models import User


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


def send_email(subject: str, body: str, user: User, sender_email: str) -> bool:
    current_app.logger.debug(
        f"SMTP settings being used: Server: {user.smtp_server}, Port: {user.smtp_port}, "
        f"Username: {user.smtp_username}"
    )
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = sender_email  # TODO this is almost certainly a bug. sent *to* the sender?
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # TODO we shouldn't return true/false but probably raise our own custom exception
    # since using a bool is less "pythonic"
    try:
        with smtplib.SMTP(user.smtp_server, user.smtp_port, timeout=10) as server:  # Added timeout
            server.starttls()
            server.login(user.smtp_username, user.smtp_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        current_app.logger.info("Email sent successfully.")
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending email: {e}", exc_info=True)
        return False
