import re
import socket
import unicodedata
from typing import Sequence

from flask import (
    current_app,
    flash,
    session,
)
from unidecode import unidecode
from wtforms import Field, Form
from wtforms.validators import ValidationError

from hushline.db import db
from hushline.email import create_smtp_config, send_email
from hushline.model import SMTPEncryption, User, Username


def valid_username(form: Form, field: Field) -> None:
    if not re.match(r"^[a-zA-Z0-9_-]+$", field.data):
        raise ValidationError(
            "Username must contain only letters, numbers, underscores, or hyphens."
        )


def _dir_sort_key(u: Username) -> str:
    s = (u._display_name or u._username or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = unidecode(s)           # Hangul, Kana, Cyrillic, etc -> Latin-ish
    return s.casefold()


def get_directory_usernames() -> Sequence[Username]:
    rows = db.session.scalars(
        db.select(Username)
        .join(User)
        .filter(Username.show_in_directory.is_(True))
    ).all()

    rows.sort(key=lambda u: (not u.user.is_admin, _dir_sort_key(u), u.id))
    return rows


def validate_captcha(captcha_answer: str) -> bool:
    if not captcha_answer.isdigit():
        flash("Incorrect CAPTCHA. Please enter a valid number.", "error")
        return False

    if captcha_answer != session.get("math_answer"):
        flash("Incorrect CAPTCHA. Please try again.", "error")
        return False

    return True


def get_ip_address() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 1))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = "127.0.0.1"
    finally:
        s.close()
    return ip_address


def do_send_email(user: User, body: str) -> None:
    if not user.email or not user.enable_email_notifications:
        return

    try:
        if user.smtp_server:
            smtp_config = create_smtp_config(
                user.smtp_username,  # type: ignore[arg-type]
                user.smtp_server,  # type: ignore[arg-type]
                user.smtp_port,  # type: ignore[arg-type]
                user.smtp_password,  # type: ignore[arg-type]
                user.smtp_sender,  # type: ignore[arg-type]
                encryption=user.smtp_encryption,
            )
        else:
            smtp_config = create_smtp_config(
                current_app.config["SMTP_USERNAME"],
                current_app.config["SMTP_SERVER"],
                current_app.config["SMTP_PORT"],
                current_app.config["SMTP_PASSWORD"],
                current_app.config["NOTIFICATIONS_ADDRESS"],
                encryption=SMTPEncryption[current_app.config["SMTP_ENCRYPTION"]],
            )

        send_email(user.email, "New Hush Line Message Received", body, smtp_config)
    except Exception as e:
        current_app.logger.error(f"Error sending email: {str(e)}", exc_info=True)
