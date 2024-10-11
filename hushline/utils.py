import smtplib
from contextlib import contextmanager
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Callable, Generator, Optional, TypeVar

from flask import abort, current_app, flash, redirect, session, url_for

from hushline.model import SMTPEncryption, User

from .db import db

T = TypeVar("T")
U = TypeVar("U")


def if_not_none(
    value: Optional[T], func: Callable[[T], U], allow_falsey: bool = True
) -> Optional[U]:
    if allow_falsey:
        if value is not None:
            return func(value)
    elif value:
        return func(value)
    return None


def parse_bool(val: str) -> bool:
    match val:
        case "true":
            return True
        case "false":
            return False
    raise ValueError(f"Unparseable boolean value: {val!r}")


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
        user = db.session.get(User, session["user_id"])
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
    sender: str

    def validate(self) -> bool:
        return all([self.username, self.server, self.port, self.password, self.sender])

    @contextmanager
    def smtp_login(self, *, timeout: int = 1) -> Generator[smtplib.SMTP, None, None]:
        raise NotImplementedError


def create_smtp_config(  # noqa PLR0913
    username: str, server: str, port: int, password: str, sender: str, *, encryption: SMTPEncryption
) -> SMTPConfig:
    match encryption:
        case SMTPEncryption.SSL:
            return SSL_SMTPConfig(username, server, port, password, sender)
        case SMTPEncryption.StartTLS:
            return StartTLS_SMTPConfig(username, server, port, password, sender)
        case _:
            raise ValueError(f"Invalid SMTP encryption protocol: {encryption.value}")


class SSL_SMTPConfig(SMTPConfig):
    @contextmanager
    def smtp_login(self, *, timeout: int = 1) -> Generator[smtplib.SMTP, None, None]:
        with smtplib.SMTP_SSL(self.server, self.port, timeout=timeout) as server:
            server.login(self.username, self.password)
            yield server


class StartTLS_SMTPConfig(SMTPConfig):
    @contextmanager
    def smtp_login(self, *, timeout: int = 1) -> Generator[smtplib.SMTP, None, None]:
        with smtplib.SMTP(self.server, self.port, timeout=timeout) as server:
            server.starttls()
            server.login(self.username, self.password)
            yield server


def send_email(to_email: str, subject: str, body: str, smtp_config: SMTPConfig) -> bool:
    current_app.logger.debug(
        f"SMTP settings being used: Server: {smtp_config.server}, "
        f"Port: {smtp_config.port}, Username: {smtp_config.username}"
    )

    message = MIMEMultipart()
    message["From"] = smtp_config.sender
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
        with smtp_config.smtp_login() as server:
            server.send_message(message)
        return True
    except smtplib.SMTPException as e:
        current_app.logger.error(f"Error sending email: {str(e)}")
        return False
