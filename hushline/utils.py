import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Callable

from flask import current_app, flash, redirect, session, url_for

from hushline.model import User


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


def generate_user_directory_json() -> None:
    try:
        users = User.query.filter_by(show_in_directory=True).all()
        users_json = [
            {
                "primary_username": user.primary_username,
                "display_name": user.display_name or user.primary_username,
                "bio": user.bio,
                "is_admin": user.is_admin,
                "is_verified": user.is_verified,
            }
            for user in users
        ]

        if current_app.static_folder:
            directory_path = os.path.join(current_app.static_folder, "data")
            if not os.path.exists(directory_path):
                os.makedirs(directory_path)

        json_file_path = os.path.join(directory_path, "users_directory.json")
        with open(json_file_path, "w") as f:
            json.dump(users_json, f, ensure_ascii=False, indent=4)

        print(f"JSON file generated successfully at {json_file_path}")
    except Exception as e:
        current_app.logger.error(f"Failed to generate JSON file: {e}")
