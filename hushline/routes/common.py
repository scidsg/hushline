import re
import smtplib
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

from hushline.content_safety import contains_disallowed_text
from hushline.db import db
from hushline.email import create_smtp_config, send_email
from hushline.model import SMTPEncryption, User, Username


def valid_username(form: Form, field: Field) -> None:
    if not re.match(r"^[a-zA-Z0-9_-]+$", field.data):
        raise ValidationError(
            "Username must contain only letters, numbers, underscores, or hyphens."
        )
    if contains_disallowed_text(field.data):
        raise ValidationError("Username includes language that is not allowed.")


def _dir_sort_key(u: Username) -> str:
    s = (u._display_name or u._username or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = unidecode(s)  # Hangul, Kana, Cyrillic, etc -> Latin-ish
    return s.casefold()


def normalized_directory_display_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def show_directory_caution_badge(
    display_name: str | None,
    *,
    is_admin: bool,
    is_verified: bool,
    is_cautious: bool = False,
) -> bool:
    if is_cautious:
        return True

    if is_admin or is_verified:
        return False

    normalized_display_name = normalized_directory_display_name(display_name)
    if not normalized_display_name:
        return False

    return normalized_display_name == "admin" or "hushline" in normalized_display_name


def get_directory_usernames() -> Sequence[Username]:
    rows = list(
        db.session.scalars(
            db.select(Username).join(User).filter(Username.show_in_directory.is_(True))
        ).all()
    )

    rows.sort(key=lambda u: (not u.user.is_admin, _dir_sort_key(u), u.id))
    return rows


def validate_captcha(captcha_answer: str) -> bool:
    if not captcha_answer.isdigit():
        flash("⛔️ Incorrect CAPTCHA. Please enter a valid number.", "error")
        return False

    if captcha_answer != session.get("math_answer"):
        flash("⛔️ Incorrect CAPTCHA. Please try again.", "error")
        return False

    return True


def get_ip_address() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 1))
        ip_address = s.getsockname()[0]
    except OSError:
        ip_address = "127.0.0.1"
    finally:
        s.close()
    return ip_address


def do_send_email(user: User, body: str) -> None:
    recipients = user.enabled_notification_recipients
    if not recipients or not user.enable_email_notifications:
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
            smtp_username = current_app.config.get("SMTP_USERNAME")
            smtp_server = current_app.config.get("SMTP_SERVER")
            smtp_port = current_app.config.get("SMTP_PORT")
            smtp_password = current_app.config.get("SMTP_PASSWORD")
            notifications_address = current_app.config.get("NOTIFICATIONS_ADDRESS")
            if not all(
                [smtp_username, smtp_server, smtp_port, smtp_password, notifications_address]
            ):
                current_app.logger.warning(
                    "Skipping email send: default SMTP is not fully configured"
                )
                return
            smtp_config = create_smtp_config(
                smtp_username,
                smtp_server,
                smtp_port,
                smtp_password,
                notifications_address,
                encryption=SMTPEncryption[current_app.config["SMTP_ENCRYPTION"]],
            )

        reply_to = current_app.config.get("NOTIFICATIONS_REPLY_TO") or current_app.config.get(
            "NOTIFICATIONS_ADDRESS"
        )
        for recipient in recipients:
            recipient_email = recipient.email
            if recipient_email is None:
                continue
            send_email(
                recipient_email,
                "New Hush Line Message Received",
                body,
                smtp_config,
                reply_to,
            )
    except (KeyError, OSError, TypeError, ValueError, smtplib.SMTPException) as e:
        current_app.logger.error(f"Error sending email: {str(e)}", exc_info=True)


def format_message_email_fields(extracted_fields: Sequence[tuple[str, str]]) -> str:
    email_body = ""
    for name, value in extracted_fields:
        email_body += f"\n\n{name}\n\n{value}\n\n=============="
    return email_body.strip()


def format_full_message_email_body(extracted_fields: Sequence[tuple[str, str]]) -> str:
    email_body = ""
    for name, value in extracted_fields:
        email_body += f"# {name}\n\n{value}\n\n====================\n\n"
    return email_body.strip()
