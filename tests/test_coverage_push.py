from __future__ import annotations

import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, Response, url_for
from flask.sessions import SecureCookieSession
from flask.testing import FlaskClient
from stripe import InvalidRequestError
from werkzeug.exceptions import ServiceUnavailable
from wtforms import Form, StringField
from wtforms.validators import DataRequired, ValidationError

import hushline.email as email_mod
import hushline.forms as forms_mod
from hushline.config import AliasMode, ConfigParseError, FieldsMode, load_config
from hushline.db import db
from hushline.model import (
    Message,
    MessageStatus,
    MessageStatusText,
    SMTPEncryption,
    Tier,
    User,
)
from hushline.premium import create_products_and_prices
from hushline.secure_session import EncryptedSessionInterface
from hushline.settings.data_export import _build_zip, _write_pgp_messages
from hushline.settings.forms import EmailForwardingForm, SetHomepageUsernameForm
from hushline.settings.notifications import handle_email_forwarding_form
from hushline.utils import if_not_none, parse_bool


class _Cfg(email_mod.SMTPConfig):
    def smtp_login(self, timeout: int = 10) -> None:  # type: ignore[override]
        _ = timeout
        raise AssertionError("smtp_login should not be called in this test")


def test_cli_stripe_configure_creates_missing_tiers(app: Flask) -> None:
    runner = app.test_cli_runner()
    app.config["STRIPE_SECRET_KEY"] = ""
    db.session.execute(db.delete(Tier))
    db.session.commit()

    with (
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe_mock,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_mock,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    assert db.session.scalar(db.select(Tier).filter_by(name="Free")) is not None
    assert db.session.scalar(db.select(Tier).filter_by(name="Business")) is not None
    init_stripe_mock.assert_not_called()
    create_mock.assert_not_called()


def test_button_widgets_and_coerce_status() -> None:
    class DummyForm(Form):
        required_field = StringField("Required", validators=[DataRequired()])

    form = DummyForm()
    button_html = str(forms_mod.Button()(form.required_field))
    assert "required" in button_html
    assert 'type="submit"' in button_html

    display_none_html = str(forms_mod.DisplayNoneButton()(form.required_field, **{"class": "x"}))
    assert "x display-none" in display_none_html

    assert forms_mod.coerce_status("pending") == MessageStatus.PENDING
    assert forms_mod.coerce_status(MessageStatus.ACCEPTED) == MessageStatus.ACCEPTED


def test_custom_validators_negative_paths() -> None:
    class DummyForm(Form):
        field = StringField("Field")

    form = DummyForm()

    complex_pw = forms_mod.ComplexPassword()
    form.field.data = "alllowercase123!"
    with pytest.raises(ValidationError):
        complex_pw(form, form.field)

    hex_color = forms_mod.HexColor()
    form.field.data = "#zzzzzz"
    with pytest.raises(ValidationError):
        hex_color(form, form.field)

    canonical = forms_mod.CanonicalHTML()
    form.field.data = " <b>unsafe</b> "
    with pytest.raises(ValidationError):
        canonical(form, form.field)


def test_email_forwarding_form_requires_email_and_smtp_fields(app: Flask) -> None:
    with (
        app.test_request_context("/settings/notifications", method="POST"),
        patch("hushline.settings.forms.FlaskForm.validate", new=lambda *_args, **_kwargs: True),
    ):
        app.config["NOTIFICATIONS_ADDRESS"] = ""
        form = EmailForwardingForm(meta={"csrf": False})
        form.forwarding_enabled.data = True
        form.email_address.data = ""
        form.custom_smtp_settings.data = True
        form.smtp_settings.smtp_sender.data = ""
        form.smtp_settings.smtp_username.data = ""
        form.smtp_settings.smtp_server.data = ""
        form.smtp_settings.smtp_port.data = None
        form.email_address.errors = []
        form.smtp_settings.smtp_sender.errors = []
        form.smtp_settings.smtp_username.errors = []
        form.smtp_settings.smtp_server.errors = []
        form.smtp_settings.smtp_port.errors = []

        assert form.validate() is False
        assert any("Email address must be specified" in err for err in form.email_address.errors)
        assert form.smtp_settings.smtp_sender.errors
        assert form.smtp_settings.smtp_username.errors
        assert form.smtp_settings.smtp_server.errors
        assert form.smtp_settings.smtp_port.errors


def test_email_forwarding_form_validate_short_circuits_when_base_invalid(app: Flask) -> None:
    with (
        app.test_request_context("/settings/notifications", method="POST"),
        patch("hushline.settings.forms.FlaskForm.validate", new=lambda *_args, **_kwargs: False),
    ):
        form = EmailForwardingForm(meta={"csrf": False})
        assert form.validate() is False


def test_set_homepage_username_form_rejects_unknown_user(app: Flask) -> None:
    with app.test_request_context("/settings/branding", method="POST"):
        form = SetHomepageUsernameForm(meta={"csrf": False}, data={"username": "no-such-user"})
        assert form.validate() is False
        assert "does not exist" in form.username.errors[0]


def test_base_smtp_config_not_implemented() -> None:
    cfg = email_mod.SMTPConfig("u", "smtp.example.com", 587, "p", "sender@example.com")
    with pytest.raises(NotImplementedError), cfg.smtp_login():
        pass


def test_is_safe_smtp_host_rejects_invalid_ip(app: Flask) -> None:
    with app.app_context(), patch(
        "hushline.email.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("not-an-ip", 0))],
    ):
        assert email_mod.is_safe_smtp_host("smtp.example.com") is False


def test_send_email_decodes_bytes_and_returns_false_when_no_attempts(app: Flask) -> None:
    smtp_secret = secrets.token_urlsafe(16)
    cfg = _Cfg(
        username="u",
        server="smtp.example.com",
        port=587,
        password=smtp_secret,
        sender="sender@example.com",
    )
    with app.app_context(), patch("hushline.email.is_safe_smtp_host", return_value=True):
        app.config["SMTP_SEND_ATTEMPTS"] = 0
        assert email_mod.send_email("to@example.com", "subject", b"bytes body", cfg) is False  # type: ignore[arg-type]


def test_message_status_text_upsert_delete_paths(app: Flask, user: User) -> None:
    with app.app_context():
        with patch("hushline.model.message_status_text.db.session.execute") as execute_mock:
            execute_mock.return_value = SimpleNamespace(rowcount=0)
            MessageStatusText.upsert(user.id, MessageStatus.PENDING, "   ")

        with (
            patch("hushline.model.message_status_text.db.session.execute") as execute_mock,
            patch("hushline.model.message_status_text.db.session.rollback") as rollback_mock,
        ):
            execute_mock.return_value = SimpleNamespace(rowcount=2)
            with pytest.raises(ServiceUnavailable):
                MessageStatusText.upsert(user.id, MessageStatus.PENDING, "")
            rollback_mock.assert_called_once()


def test_encrypted_session_invalid_token_invalid_json_and_missing_key(app: Flask) -> None:
    interface = EncryptedSessionInterface()
    app.config["SESSION_FERNET_KEY"] = Fernet.generate_key().decode("utf-8")
    cookie_name = app.config.get("SESSION_COOKIE_NAME", "__HOST-session")

    fake_bad_token_fernet = SimpleNamespace(
        decrypt=lambda *_args, **_kwargs: (_ for _ in ()).throw(InvalidToken())
    )
    fake_request = SimpleNamespace(cookies={cookie_name: "opaque"})
    with patch.object(interface, "_get_fernet", return_value=fake_bad_token_fernet):
        opened = interface.open_session(app, request=fake_request)  # type: ignore[arg-type]
    assert isinstance(opened, SecureCookieSession)
    assert dict(opened) == {}

    with patch.object(
        interface,
        "_get_fernet",
        return_value=SimpleNamespace(decrypt=lambda *_args, **_kwargs: b"this is not json"),
    ):
        opened = interface.open_session(app, request=fake_request)  # type: ignore[arg-type]
    assert isinstance(opened, SecureCookieSession)
    assert dict(opened) == {}

    app.config["SESSION_FERNET_KEY"] = None
    session_data = SecureCookieSession({"x": "y"})
    session_data.modified = True
    response = Response()
    with pytest.raises(RuntimeError, match="Fernet key not set"):
        interface.save_session(app, session_data, response)


@pytest.mark.usefixtures("_authenticated_user")
def test_data_export_invalid_form_returns_400(client, app: Flask) -> None:  # type: ignore[no-untyped-def]
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        response = client.post(url_for("settings.data_export"))
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_data_export_encrypt_requires_pgp(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(url_for("settings.data_export"), data={"encrypt_export": "y"})
    assert response.status_code == 302
    assert response.location == url_for("settings.encryption", _external=False)


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_data_export_encrypt_failure_redirects_to_advanced(client) -> None:  # type: ignore[no-untyped-def]
    with patch("hushline.settings.data_export.encrypt_bytes", return_value=None):
        response = client.post(url_for("settings.data_export"), data={"encrypt_export": "y"})
    assert response.status_code == 302
    assert response.location == url_for("settings.advanced", _external=False)


def test_build_zip_skips_non_pgp_and_unencrypted_values(app: Flask, user: User) -> None:
    with app.app_context():
        attached_user = db.session.get(User, user.id)
        assert attached_user is not None

        msg = Message(username_id=attached_user.primary_username.id)
        db.session.add(msg)
        db.session.commit()

        plain = attached_user.primary_username.message_fields[-1]
        from hushline.crypto import encrypt_field
        from hushline.model import FieldValue

        fv = FieldValue(plain, msg, "not encrypted", False)
        db.session.add(fv)
        db.session.commit()
        fv.encrypted = True
        fv._value = encrypt_field("definitely not pgp") or ""
        db.session.commit()

        payload = _build_zip(user.id)
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(payload)) as zip_file:
            assert not [n for n in zip_file.namelist() if n.startswith("pgp_messages/")]


def test_write_pgp_messages_handles_empty_username_ids() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        _write_pgp_messages(zip_file, [])
        assert zip_file.namelist() == []


def test_write_pgp_messages_skips_unencrypted_field_values(app: Flask, user: User) -> None:
    import io
    import zipfile

    with app.app_context():
        attached_user = db.session.get(User, user.id)
        assert attached_user is not None
        msg = Message(username_id=attached_user.primary_username.id)
        db.session.add(msg)
        db.session.commit()

        from hushline.model import FieldValue

        fv = FieldValue(attached_user.primary_username.message_fields[-1], msg, "plain", False)
        db.session.add(fv)
        db.session.commit()

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            _write_pgp_messages(zip_file, [attached_user.primary_username.id])
            assert not [name for name in zip_file.namelist() if name.startswith("pgp_messages/")]


def test_user_alias_mode_edge_cases(app: Flask, user: User) -> None:
    with app.app_context():
        user.tier_id = Tier.free_tier_id()
        app.config["ALIAS_MODE"] = AliasMode.PREMIUM
        assert user.max_aliases == 0

        user.tier_id = 999
        app.config["FLASK_ENV"] = "production"
        with patch.object(app.logger, "warning") as warning_log:
            assert user.max_aliases == 100
            warning_log.assert_called()

        app.config["FLASK_ENV"] = "development"
        with pytest.raises(Exception, match="Unknown tier id"):
            _ = user.max_aliases

        app.config["ALIAS_MODE"] = "bogus"
        app.config["FLASK_ENV"] = "production"
        with patch.object(app.logger, "warning") as warning_log:
            assert user.max_aliases == 100
            warning_log.assert_called()

        app.config["FLASK_ENV"] = "development"
        with pytest.raises(Exception, match="Unhandled alias mode"):
            _ = user.max_aliases


def test_user_init_rejects_direct_password_hash_assignment() -> None:
    forbidden_hash = "x"
    pw = secrets.token_urlsafe(16)
    with pytest.raises(ValueError, match="cannot be mannually set"):
        User(password_hash=forbidden_hash, password=pw)


def test_health_json_route(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/health.json")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_load_config_additional_branches() -> None:
    cfg = load_config({})
    assert cfg["ALIAS_MODE"] == AliasMode.ALWAYS
    assert cfg["FIELDS_MODE"] == FieldsMode.ALWAYS

    cfg = load_config({"SQLALCHEMY_DATABASE_URI": "postgresql://u:p@h/db"})
    assert cfg["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://")

    with pytest.raises(ConfigParseError, match="Not a valid value for FieldsMode"):
        load_config({"FIELDS_MODE": "invalid-mode"})


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_toggle_false_paths(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        url_for("settings.registration"),
        data={"registration_enabled": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration disabled." in response.text

    response = client.post(
        url_for("settings.registration"),
        data={"registration_codes_required": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration codes not required." in response.text


def test_blob_storage_none_driver_when_missing_config() -> None:
    from hushline.storage import BlobStorage

    app = Flask(__name__)
    store = BlobStorage()
    store.init_app(app)
    assert app.extensions["BLOB_STORAGE"] is None


def test_encrypt_helpers_branch_types(app: Flask, mocker) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        mocker.patch("hushline.crypto.Cert.from_bytes", return_value=object())
        mocker.patch("hushline.crypto.encrypt", return_value=b"ciphertext")
        from hushline import crypto

        assert crypto.encrypt_message("hello", "key") == "ciphertext"

        mocker.patch("hushline.crypto.encrypt", return_value="ciphertext")
        assert crypto.encrypt_bytes(b"hello", "key") == b"ciphertext"


def test_handle_email_forwarding_form_smtp_validation_exception(app: Flask, user: User) -> None:
    user.pgp_key = "fake-pgp"
    form = EmailForwardingForm(meta={"csrf": False})
    form.email_address.data = "test@example.com"
    form.custom_smtp_settings.data = True
    form.smtp_settings.smtp_server.data = "smtp.example.com"
    form.smtp_settings.smtp_port.data = 587
    form.smtp_settings.smtp_username.data = "user"
    form.smtp_settings.smtp_password.data = "password"
    form.smtp_settings.smtp_sender.data = "sender@example.com"
    form.smtp_settings.smtp_encryption.data = SMTPEncryption.StartTLS.name

    bad_cfg = SimpleNamespace(smtp_login=lambda: (_ for _ in ()).throw(OSError("boom")))
    with (
        app.test_request_context("/settings/notifications", method="POST"),
        patch("hushline.settings.notifications.is_safe_smtp_host", return_value=True),
        patch("hushline.settings.notifications.create_smtp_config", return_value=bad_cfg),
    ):
        assert handle_email_forwarding_form(user, form) is None


@pytest.mark.usefixtures("_authenticated_user")
def test_notifications_toggle_false_flash_paths(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(url_for("settings.notifications"), data={"toggle_notifications": ""})
    assert response.status_code == 302

    response = client.post(
        url_for("settings.notifications"),
        data={"toggle_include_content": ""},
    )
    assert response.status_code == 302

    response = client.post(
        url_for("settings.notifications"),
        data={"toggle_encrypt_entire_body": ""},
    )
    assert response.status_code == 302


@pytest.mark.usefixtures("_authenticated_user")
def test_notifications_toggle_include_content_true_path(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        url_for("settings.notifications"),
        data={"toggle_include_content": "", "include_content": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Email message content enabled" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_authentication_required_redirects_to_2fa_when_not_authenticated(
    client: FlaskClient, user: User
) -> None:  # type: ignore[no-untyped-def]
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["session_id"] = user.session_id
        sess["username"] = user.primary_username.username
        sess["is_authenticated"] = False

    response = client.get(url_for("settings.profile"))
    assert response.status_code == 302
    assert "/verify-2fa-login" in response.location


@pytest.mark.usefixtures("_authenticated_user")
def test_admin_authentication_required_forbids_non_admin(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(url_for("settings.admin"))
    assert response.status_code == 403


def test_create_products_and_prices_finds_product_in_list(app: Flask) -> None:
    tier = Tier.business_tier()
    assert tier is not None
    tier.stripe_product_id = "prod_missing"
    tier.stripe_price_id = None
    db.session.commit()

    with (
        patch(
            "hushline.premium.stripe.Product.retrieve",
            side_effect=InvalidRequestError("missing", param=""),
        ),
        patch(
            "hushline.premium.stripe.Product.list",
            return_value=[SimpleNamespace(id="prod_found", name=tier.name, default_price=None)],
        ),
        patch("hushline.premium.stripe.Product.create", return_value=MagicMock(id="prod_new")),
        patch("hushline.premium.stripe.Price.create", return_value=MagicMock(id="price_new")),
    ):
        create_products_and_prices()

    db.session.refresh(tier)
    assert tier.stripe_product_id == "prod_found"
    assert tier.stripe_price_id == "price_new"


def test_create_products_and_prices_reuses_existing_default_price(app: Flask) -> None:
    tier = Tier.business_tier()
    assert tier is not None
    tier.stripe_product_id = "prod_ok"
    tier.stripe_price_id = None
    db.session.commit()

    with (
        patch(
            "hushline.premium.stripe.Product.retrieve",
            return_value=MagicMock(id="prod_ok", default_price="price_default"),
        ),
        patch(
            "hushline.premium.stripe.Price.retrieve",
            return_value=MagicMock(id="price_default", unit_amount=2550),
        ),
        patch("hushline.premium.stripe.Price.create") as price_create_mock,
    ):
        create_products_and_prices()

    db.session.refresh(tier)
    assert tier.stripe_price_id == "price_default"
    assert tier.monthly_amount == 2550
    price_create_mock.assert_not_called()


def test_create_products_and_prices_price_already_exists_path(app: Flask) -> None:
    tier = Tier.business_tier()
    assert tier is not None
    tier.stripe_product_id = "prod_ok"
    tier.stripe_price_id = "price_ok"
    db.session.commit()

    with (
        patch(
            "hushline.premium.stripe.Product.retrieve",
            return_value=MagicMock(id="prod_ok", default_price=None),
        ),
        patch("hushline.premium.stripe.Price.retrieve", return_value=MagicMock(id="price_ok")),
        patch("hushline.premium.stripe.Price.create") as price_create_mock,
    ):
        create_products_and_prices()

    price_create_mock.assert_not_called()


def test_create_products_and_prices_recreates_price_when_existing_id_invalid(app: Flask) -> None:
    tier = Tier.business_tier()
    assert tier is not None
    tier.stripe_product_id = "prod_ok"
    tier.stripe_price_id = "price_stale"
    db.session.commit()

    with (
        patch(
            "hushline.premium.stripe.Product.retrieve",
            return_value=SimpleNamespace(id="prod_ok", default_price=None),
        ),
        patch(
            "hushline.premium.stripe.Price.retrieve",
            side_effect=InvalidRequestError("missing", param=""),
        ),
        patch("hushline.premium.stripe.Price.create", return_value=SimpleNamespace(id="price_new")),
    ):
        create_products_and_prices()

    db.session.refresh(tier)
    assert tier.stripe_price_id == "price_new"


def test_utils_if_not_none_and_parse_bool() -> None:
    assert if_not_none(0, lambda x: x + 1) == 1
    assert if_not_none("", lambda x: x + "z", allow_falsey=False) is None
    assert if_not_none("x", lambda x: x + "z", allow_falsey=False) == "xz"
    assert parse_bool("true") is True
    assert parse_bool("false") is False
