import ipaddress
import smtplib
import socket
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Generator

from flask import current_app

from hushline.model import SMTPEncryption


class _SMTP(smtplib.SMTP):
    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        # socket.create_connection gives every resolved address the full timeout.
        # Share one budget so multiple unreachable addresses cannot kill the web worker.
        if timeout <= 0:
            raise ValueError("SMTP connection timeout must be positive")
        deadline = time.monotonic() + timeout
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        last_error: OSError | None = None
        for family, socktype, proto, _, address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("SMTP connection timed out")
            sock = None
            try:
                sock = socket.socket(family, socktype, proto)
                sock.settimeout(remaining)
                if self.source_address:
                    sock.bind(self.source_address)
                sock.connect(address)
                sock.settimeout(timeout)
                return sock
            except OSError as error:
                if sock is not None:
                    sock.close()
                last_error = error
        if last_error is not None:
            raise last_error
        raise OSError("SMTP server did not resolve to any addresses")


class _SMTP_SSL(smtplib.SMTP_SSL, _SMTP):
    # SMTP_SSL wraps the socket from super()._get_socket with the original
    # hostname, preserving TLS SNI and the SSL context's verification behavior.
    pass


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
        with _SMTP_SSL(self.server, self.port, timeout=timeout) as server:
            server.ehlo()
            server.login(self.username, self.password)
            yield server


class StartTLS_SMTPConfig(SMTPConfig):
    @contextmanager
    def smtp_login(self, timeout: int = 10) -> Generator[smtplib.SMTP, None, None]:
        with _SMTP(self.server, self.port, timeout=timeout) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(self.username, self.password)
            yield server


def is_safe_smtp_host(host: str) -> bool:
    if not host:
        current_app.logger.warning("SMTP server validation failed: empty host")
        return False

    if host.lower() == "localhost":
        current_app.logger.warning("SMTP server validation failed: localhost is not allowed")
        return False

    try:
        addrinfo = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as e:
        current_app.logger.warning(f"SMTP server validation failed: {host!r} unresolved ({e})")
        return False

    for _, _, _, _, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            current_app.logger.warning(
                f"SMTP server validation failed: invalid IP {ip_str!r} for host {host!r}"
            )
            return False
        if not ip.is_global:
            current_app.logger.warning(
                f"SMTP server validation failed: {host!r} resolved to non-public IP {ip}"
            )
            return False

    return True


def send_email(
    to_email: str, subject: str, body: str, smtp_config: SMTPConfig, reply_to: str | None = None
) -> bool:
    if not is_safe_smtp_host(smtp_config.server):
        current_app.logger.error(f"Blocked SMTP delivery to unsafe host {smtp_config.server!r}")
        return False
    current_app.logger.debug(
        f"SMTP settings being used: Server: {smtp_config.server}, "
        f"Port: {smtp_config.port}, Username: {smtp_config.username}"
    )

    # Check if body is a bytes object
    if isinstance(body, bytes):
        # Decode the bytes object to a string
        body = body.decode("utf-8")

    # Keep single-part bodies single-part. PGP/Inline clients expect the armored
    # block to be the text body, not hidden inside a multipart wrapper.
    message = MIMEText(body, "plain")
    message["From"] = smtp_config.sender
    message["To"] = to_email
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to

    if not smtp_config.validate():
        current_app.logger.error("SMTP server or port is not set.")
        return False

    timeout = int(current_app.config.get("SMTP_TIMEOUT", 10))
    attempts = int(current_app.config.get("SMTP_SEND_ATTEMPTS", 3))
    retry_delay = float(current_app.config.get("SMTP_SEND_RETRY_DELAY_SEC", 2))

    for attempt in range(1, attempts + 1):
        message_submission_attempted = False
        try:
            with smtp_config.smtp_login(timeout=timeout) as server:
                message_submission_attempted = True
                refusals = server.send_message(message)
            if refusals:
                current_app.logger.error(f"SMTP refused recipients: {refusals}")
                raise smtplib.SMTPRecipientsRefused(refusals)
            return True
        except smtplib.SMTPException as e:
            current_app.logger.error(
                f"Error sending email (attempt {attempt}/{attempts}): {str(e)}"
            )
            if message_submission_attempted:
                current_app.logger.error(
                    "Not retrying SMTP send after message submission attempt to avoid "
                    "duplicate delivery."
                )
                return False
            if attempt < attempts:
                time.sleep(retry_delay)
                continue
            return False
    return False
