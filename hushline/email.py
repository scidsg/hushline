import smtplib
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Generator

from flask import current_app

from hushline.model import SMTPEncryption


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
    def smtp_login(self, timeout: int = 10) -> Generator[smtplib.SMTP, None, None]:
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
    def smtp_login(self, timeout: int = 10) -> Generator[smtplib.SMTP, None, None]:
        with smtplib.SMTP_SSL(self.server, self.port, timeout=timeout) as server:
            server.ehlo()
            server.login(self.username, self.password)
            yield server


class StartTLS_SMTPConfig(SMTPConfig):
    @contextmanager
    def smtp_login(self, timeout: int = 10) -> Generator[smtplib.SMTP, None, None]:
        with smtplib.SMTP(self.server, self.port, timeout=timeout) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
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

    timeout = int(current_app.config.get("SMTP_TIMEOUT", 10))
    attempts = int(current_app.config.get("SMTP_SEND_ATTEMPTS", 3))
    retry_delay = float(current_app.config.get("SMTP_SEND_RETRY_DELAY_SEC", 2))

    for attempt in range(1, attempts + 1):
        try:
            with smtp_config.smtp_login(timeout=timeout) as server:
                refusals = server.send_message(message)
            if refusals:
                current_app.logger.error(f"SMTP refused recipients: {refusals}")
                raise smtplib.SMTPRecipientsRefused(refusals)
            return True
        except smtplib.SMTPException as e:
            current_app.logger.error(
                f"Error sending email (attempt {attempt}/{attempts}): {str(e)}"
            )
            if attempt < attempts:
                time.sleep(retry_delay)
                continue
            return False
