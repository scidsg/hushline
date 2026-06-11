import re
import smtplib
import socket
import unicodedata
from collections.abc import Callable, Sequence

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
from hushline.model import NotificationRecipient, SMTPEncryption, User, Username

RecipientEmailBody = str | Callable[[NotificationRecipient], str | None]


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


_DIRECTORY_CONFUSABLE_ASCII = str.maketrans(
    {
        # The caution badge only protects names resembling these ASCII terms:
        # "admin" and "hushline". Normalize common Unicode homoglyphs for
        # those letters before transliteration so spoofed names are not missed.
        "Α": "a",
        "А": "a",
        "а": "a",
        "Ꭺ": "a",
        "ꓮ": "a",
        "ԁ": "d",
        "Ꭰ": "d",
        "Η": "h",
        "Н": "h",
        "н": "h",
        "Һ": "h",
        "һ": "h",
        "Ꮋ": "h",
        "Ꮒ": "h",
        "Ι": "i",
        "І": "i",
        "і": "i",
        "Ӏ": "l",
        "ӏ": "l",
        "ı": "i",
        "Ꭵ": "i",
        "ⅼ": "l",
        "Ⲓ": "l",
        "ⲓ": "l",
        "Μ": "m",
        "М": "m",
        "м": "m",
        "Ꮇ": "m",
        "ꓟ": "m",
        "Ν": "n",
        "п": "n",
        "ո": "n",
        "Ꮑ": "n",
        "Ѕ": "s",
        "ѕ": "s",
        "Ꮪ": "s",
        "ꓢ": "s",
        "υ": "u",
        "Ս": "u",
        "ս": "u",
        "⋃": "u",
        "Ε": "e",
        "Е": "e",
        "е": "e",
        "Ꭼ": "e",
    }
)


def normalized_directory_display_name(value: str | None) -> str:
    normalized_value = unicodedata.normalize("NFKC", value or "")
    skeleton = normalized_value.translate(_DIRECTORY_CONFUSABLE_ASCII)
    transliterated = unidecode(skeleton)
    return re.sub(r"[^a-z0-9]+", "", transliterated.casefold())


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


def send_email_to_user_recipients(user: User, subject: str, body: RecipientEmailBody) -> None:
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
        delivered_email_addresses: set[str] = set()
        for recipient in recipients:
            recipient_email = recipient.email
            if recipient_email is None:
                continue
            normalized_recipient_email = recipient_email.strip().casefold()
            if normalized_recipient_email in delivered_email_addresses:
                current_app.logger.warning(
                    "Skipping duplicate notification recipient email for user %s", user.id
                )
                continue
            recipient_body = body(recipient) if callable(body) else body
            if not recipient_body:
                continue
            try:
                if send_email(
                    recipient_email,
                    subject,
                    recipient_body,
                    smtp_config,
                    reply_to,
                ):
                    delivered_email_addresses.add(normalized_recipient_email)
            except (OSError, TypeError, ValueError, smtplib.SMTPException) as e:
                current_app.logger.error(
                    "Error sending email to %s: %s", recipient_email, str(e), exc_info=True
                )
    except (KeyError, OSError, TypeError, ValueError, smtplib.SMTPException) as e:
        current_app.logger.error(f"Error sending email: {str(e)}", exc_info=True)


def do_send_email(user: User, body: str) -> None:
    send_email_to_user_recipients(user, "New Hush Line Message Received", body)


def notification_email_encryption_target(user: User) -> str | list[str] | None:
    return user.message_encryption_target


def notification_recipient_encryption_target(
    user: User, recipient: NotificationRecipient
) -> str | None:
    if recipient.pgp_key:
        return recipient.pgp_key

    if recipient.position == 0 and user.pgp_key:
        return user.pgp_key

    primary_recipient = user.primary_notification_recipient
    if primary_recipient is not None and primary_recipient.id == recipient.id and user.pgp_key:
        return user.pgp_key

    return None


def notification_recipient_public_key_entries(user: User) -> list[dict[str, int | str]]:
    entries: list[dict[str, int | str]] = []
    for recipient in user.enabled_notification_recipients:
        if recipient.id is None:
            continue
        if key := notification_recipient_encryption_target(user, recipient):
            entries.append({"id": recipient.id, "key": key})
    return entries


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
