import secrets
import smtplib
from contextlib import contextmanager
from typing import Generator, cast
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import hushline.email as email_mod
from hushline.model import SMTPEncryption


def test_create_smtp_config_variants() -> None:
    cfg_ssl = email_mod.create_smtp_config(
        "u", "smtp.example.com", 465, "p", "sender@example.com", encryption=SMTPEncryption.SSL
    )
    assert isinstance(cfg_ssl, email_mod.SSL_SMTPConfig)

    cfg_starttls = email_mod.create_smtp_config(
        "u",
        "smtp.example.com",
        587,
        "p",
        "sender@example.com",
        encryption=SMTPEncryption.StartTLS,
    )
    assert isinstance(cfg_starttls, email_mod.StartTLS_SMTPConfig)


def test_create_smtp_config_invalid_encryption() -> None:
    class UnknownEncryption:
        value = "UNKNOWN"

    with pytest.raises(ValueError, match="Invalid SMTP encryption protocol"):
        email_mod.create_smtp_config(
            "u",
            "smtp.example.com",
            587,
            "p",
            "sender@example.com",
            encryption=UnknownEncryption(),  # type: ignore[arg-type]
        )


def test_is_safe_smtp_host_validation(app: Flask) -> None:
    with app.app_context():
        assert email_mod.is_safe_smtp_host("") is False
        assert email_mod.is_safe_smtp_host("localhost") is False

        with patch("hushline.email.socket.getaddrinfo", side_effect=OSError("dns fail")):
            assert email_mod.is_safe_smtp_host("smtp.example.com") is False

        with patch(
            "hushline.email.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("127.0.0.1", 0))],
        ):
            assert email_mod.is_safe_smtp_host("smtp.example.com") is False

        with patch(
            "hushline.email.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("8.8.8.8", 0))],
        ):
            assert email_mod.is_safe_smtp_host("smtp.example.com") is True


def test_send_email_rejects_unsafe_host(app: Flask) -> None:
    cfg = email_mod.create_smtp_config(
        "u",
        "smtp.example.com",
        587,
        "p",
        "sender@example.com",
        encryption=SMTPEncryption.StartTLS,
    )
    with app.app_context(), patch("hushline.email.is_safe_smtp_host", return_value=False):
        assert email_mod.send_email("to@example.com", "subject", "body", cfg) is False


def test_send_email_returns_false_when_config_invalid(app: Flask) -> None:
    cfg = email_mod.create_smtp_config(
        "",  # invalid
        "smtp.example.com",
        587,
        "p",
        "sender@example.com",
        encryption=SMTPEncryption.StartTLS,
    )
    with app.app_context(), patch("hushline.email.is_safe_smtp_host", return_value=True):
        assert email_mod.send_email("to@example.com", "subject", "body", cfg) is False


class _DummyConfig(email_mod.SMTPConfig):
    def __init__(self, *, smtp_server: MagicMock, valid: bool = True) -> None:
        smtp_secret = secrets.token_urlsafe(16)
        super().__init__(
            username="u",
            server="smtp.example.com",
            port=587,
            password=smtp_secret,
            sender="sender@example.com",
        )
        self._smtp_server = smtp_server
        self._valid = valid

    def validate(self) -> bool:
        return self._valid

    @contextmanager
    def smtp_login(self, timeout: int = 10) -> Generator[smtplib.SMTP, None, None]:
        _ = timeout
        yield cast(smtplib.SMTP, self._smtp_server)


def test_send_email_success_and_retry(app: Flask) -> None:
    smtp_server = MagicMock()
    smtp_server.send_message.side_effect = [smtplib.SMTPException("transient"), {}]
    cfg = _DummyConfig(smtp_server=smtp_server)

    with (
        app.app_context(),
        patch("hushline.email.is_safe_smtp_host", return_value=True),
        patch("hushline.email.time.sleep") as sleep_mock,
    ):
        app.config["SMTP_SEND_ATTEMPTS"] = 2
        app.config["SMTP_SEND_RETRY_DELAY_SEC"] = 0
        assert email_mod.send_email("to@example.com", "subject", "body", cfg) is True
        sleep_mock.assert_called_once()


def test_send_email_recipient_refusal_returns_false(app: Flask) -> None:
    smtp_server = MagicMock()
    smtp_server.send_message.return_value = {"to@example.com": (550, "refused")}
    cfg = _DummyConfig(smtp_server=smtp_server)

    with app.app_context(), patch("hushline.email.is_safe_smtp_host", return_value=True):
        app.config["SMTP_SEND_ATTEMPTS"] = 1
        assert email_mod.send_email("to@example.com", "subject", "body", cfg) is False
