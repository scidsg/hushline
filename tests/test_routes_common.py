from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from wtforms.validators import ValidationError

from hushline.db import db
from hushline.model import User
from hushline.routes import common as routes_common


def test_valid_username_validator() -> None:
    valid_field = MagicMock(data="name_123-abc")
    routes_common.valid_username(MagicMock(), valid_field)

    invalid_field = MagicMock(data="not valid!")
    with pytest.raises(ValidationError, match="Username must contain only"):
        routes_common.valid_username(MagicMock(), invalid_field)

    blocked_field = MagicMock(data="blocked-token")
    with (
        patch("hushline.routes.common.contains_disallowed_text", return_value=True),
        pytest.raises(ValidationError, match="not allowed"),
    ):
        routes_common.valid_username(MagicMock(), blocked_field)


def test_get_directory_usernames_sorts_admin_first_and_normalized(
    user: User, user2: User, admin_user: User
) -> None:
    admin_user.primary_username.display_name = "Zulu"
    admin_user.primary_username.show_in_directory = True
    user.primary_username.display_name = "Eclair"
    user.primary_username.show_in_directory = True
    user2.primary_username.display_name = "eclair"
    user2.primary_username.show_in_directory = True
    db.session.commit()

    rows = routes_common.get_directory_usernames()
    assert rows[0].id == admin_user.primary_username.id
    assert {rows[1].id, rows[2].id} == {user.primary_username.id, user2.primary_username.id}


def test_validate_captcha(app: Flask) -> None:
    with app.test_request_context("/"):
        from flask import session

        session["math_answer"] = "12"
        assert not routes_common.validate_captcha("abc")
        assert not routes_common.validate_captcha("7")
        assert routes_common.validate_captcha("12")


def test_get_ip_address_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = MagicMock()
    sock.getsockname.return_value = ("10.20.30.40", 12345)
    monkeypatch.setattr("hushline.routes.common.socket.socket", lambda *args: sock)
    assert routes_common.get_ip_address() == "10.20.30.40"
    sock.close.assert_called_once()


def test_get_ip_address_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = MagicMock()
    sock.connect.side_effect = OSError("fail")
    monkeypatch.setattr("hushline.routes.common.socket.socket", lambda *args: sock)
    assert routes_common.get_ip_address() == "127.0.0.1"
    sock.close.assert_called_once()


def test_do_send_email_returns_early_without_enabled_notifications(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.email = None
    user.enable_email_notifications = False

    create_smtp_config = MagicMock()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    routes_common.do_send_email(user, "body")
    create_smtp_config.assert_not_called()
    send_email.assert_not_called()


def test_do_send_email_uses_user_custom_smtp(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email = "person@example.com"
    user.smtp_server = "smtp.custom.example"
    user.smtp_port = 465
    user.smtp_username = "user1"
    user.smtp_password = "pw1"
    user.smtp_sender = "sender@example.com"

    create_smtp_config = MagicMock(return_value=MagicMock())
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    with app.app_context():
        routes_common.do_send_email(user, "body")

    create_smtp_config.assert_called_once()
    send_email.assert_called_once()


def test_do_send_email_uses_default_smtp(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email = "person@example.com"
    user.smtp_server = None

    app.config["SMTP_USERNAME"] = "default-user"
    app.config["SMTP_SERVER"] = "smtp.default.example"
    app.config["SMTP_PORT"] = 587
    app.config["SMTP_PASSWORD"] = "default-pass"
    app.config["NOTIFICATIONS_ADDRESS"] = "notify@example.com"
    app.config["NOTIFICATIONS_REPLY_TO"] = "reply@example.com"
    app.config["SMTP_ENCRYPTION"] = "StartTLS"

    create_smtp_config = MagicMock(return_value=MagicMock())
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    with app.app_context():
        routes_common.do_send_email(user, "body")

    create_smtp_config.assert_called_once()
    send_email.assert_called_once_with(
        user.email,
        "New Hush Line Message Received",
        "body",
        create_smtp_config.return_value,
        "reply@example.com",
    )


def test_do_send_email_uses_notifications_address_as_reply_to_fallback(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email = "person@example.com"
    user.smtp_server = None

    app.config["SMTP_USERNAME"] = "default-user"
    app.config["SMTP_SERVER"] = "smtp.default.example"
    app.config["SMTP_PORT"] = 587
    app.config["SMTP_PASSWORD"] = "default-pass"
    app.config["NOTIFICATIONS_ADDRESS"] = "notify@example.com"
    app.config.pop("NOTIFICATIONS_REPLY_TO", None)
    app.config["SMTP_ENCRYPTION"] = "StartTLS"

    create_smtp_config = MagicMock(return_value=MagicMock())
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    with app.app_context():
        routes_common.do_send_email(user, "body")

    send_email.assert_called_once_with(
        user.email,
        "New Hush Line Message Received",
        "body",
        create_smtp_config.return_value,
        "notify@example.com",
    )


def test_do_send_email_catches_errors(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email = "person@example.com"
    user.smtp_server = None

    app.config["SMTP_USERNAME"] = "default-user"
    app.config["SMTP_SERVER"] = "smtp.default.example"
    app.config["SMTP_PORT"] = 587
    app.config["SMTP_PASSWORD"] = "default-pass"
    app.config["NOTIFICATIONS_ADDRESS"] = "notify@example.com"
    app.config["SMTP_ENCRYPTION"] = "StartTLS"

    monkeypatch.setattr(
        "hushline.routes.common.create_smtp_config", MagicMock(side_effect=ValueError)
    )
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    with app.app_context():
        routes_common.do_send_email(user, "body")

    send_email.assert_not_called()


def test_do_send_email_skips_when_default_smtp_incomplete(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email = "person@example.com"
    user.smtp_server = None

    app.config.pop("SMTP_USERNAME", None)
    app.config["SMTP_SERVER"] = "smtp.default.example"
    app.config["SMTP_PORT"] = 587
    app.config["SMTP_PASSWORD"] = "default-pass"
    app.config["NOTIFICATIONS_ADDRESS"] = "notify@example.com"
    app.config["SMTP_ENCRYPTION"] = "StartTLS"

    create_smtp_config = MagicMock()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    with app.app_context(), patch.object(app.logger, "warning") as warning_log:
        routes_common.do_send_email(user, "body")

    create_smtp_config.assert_not_called()
    send_email.assert_not_called()
    warning_log.assert_called_once_with("Skipping email send: default SMTP is not fully configured")


def test_formatters() -> None:
    extracted_fields = [("Contact Method", "Signal"), ("Message", "Hello")]

    field_body = routes_common.format_message_email_fields(extracted_fields)
    assert "Contact Method" in field_body
    assert "Message" in field_body
    assert "==============" in field_body

    full_body = routes_common.format_full_message_email_body(extracted_fields)
    assert "# Contact Method" in full_body
    assert "# Message" in full_body
    assert "====================" in full_body
