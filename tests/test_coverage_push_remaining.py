from __future__ import annotations

import asyncio
import logging
import os
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from werkzeug.exceptions import NotFound

from hushline import create_app as create_hushline_app
from hushline import crypto, register_error_handlers
from hushline.db import db
from hushline.model import (
    FieldType,
    FieldValue,
    InviteCode,
    Message,
    StripeInvoice,
    Tier,
    User,
)
from hushline.model.enums import FieldType as EnumFieldType
from hushline.model.enums import MessageStatus
from hushline.premium import worker
from hushline.settings.common import _is_blocked_ip, _is_safe_verification_url, handle_field_post
from hushline.settings.forms import DeleteAliasForm, DeleteBrandLogoForm


def test_enums_defensive_paths() -> None:
    assert MessageStatus.default() == MessageStatus.PENDING
    fake_status = SimpleNamespace(
        PENDING=object(),
        ACCEPTED=object(),
        DECLINED=object(),
        ARCHIVED=object(),
    )
    display_str_prop = cast(property, MessageStatus.__dict__["display_str"])
    emoji_prop = cast(property, MessageStatus.__dict__["emoji"])
    default_text_prop = cast(property, MessageStatus.__dict__["default_text"])
    assert display_str_prop.fget is not None
    assert emoji_prop.fget is not None
    assert default_text_prop.fget is not None
    with pytest.raises(Exception, match="Programming error"):
        _ = display_str_prop.fget(fake_status)
    with pytest.raises(Exception, match="Programming error"):
        _ = emoji_prop.fget(fake_status)
    with pytest.raises(Exception, match="Programming error"):
        _ = default_text_prop.fget(fake_status)

    fake_field_type = SimpleNamespace(
        TEXT=object(),
        MULTILINE_TEXT=object(),
        CHOICE_SINGLE=object(),
        CHOICE_MULTIPLE=object(),
    )
    with pytest.raises(Exception, match="Programming error"):
        EnumFieldType.label(fake_field_type)  # type: ignore[arg-type]


def test_model_repr_and_field_definition_move_up_noop(user: User) -> None:
    invite = InviteCode()
    assert "<InviteCode " in repr(invite)
    assert "<Username " in repr(user.primary_username)
    field = user.primary_username.message_fields[0]
    field.sort_order = 0
    db.session.commit()
    field.move_up()
    assert field.sort_order == 0
    assert "FieldDefinition" in repr(field)


def test_field_value_remaining_paths(user: User) -> None:
    msg = Message(username_id=user.primary_username.id)
    db.session.add(msg)
    db.session.commit()

    field_def = user.primary_username.message_fields[-1]
    fv = FieldValue(field_def, msg, "x", False)
    db.session.add(fv)
    fv.value = ["a", "b"]  # type: ignore[assignment]
    assert "a\nb" in (fv.value or "")
    assert "FieldValue" in repr(fv)

    user.pgp_key = None
    db.session.commit()
    fv.encrypted = True
    with pytest.raises(ValueError, match="does not have a PGP key"):
        fv.value = "secret"

    with patch("hushline.model.field_value.encrypt_field", return_value=None):
        fv.encrypted = False
        fv.value = "plaintext"
        assert fv._value == ""


def test_hushline_init_remaining_paths(app) -> None:  # type: ignore[no-untyped-def]
    with (
        patch.dict(os.environ, {"FLASK_DEBUG": "1"}),
        patch.object(logging.Logger, "setLevel") as set_level_mock,
    ):
        extra_app = create_hushline_app(dict(app.config))
        assert isinstance(extra_app, Flask)
        set_level_mock.assert_any_call(logging.DEBUG)

    debug_app = Flask(__name__)
    debug_app.config["DEBUG"] = True
    debug_app.config["TESTING"] = False
    register_error_handlers(debug_app)
    assert Exception not in debug_app.error_handler_spec[None][None]

    normal_app = Flask(__name__)
    normal_app.config["DEBUG"] = False
    normal_app.config["TESTING"] = False
    register_error_handlers(normal_app)
    generic_handler = normal_app.error_handler_spec[None][None][Exception]
    not_found = NotFound()
    assert generic_handler(not_found) is not_found


def test_crypto_encrypt_message_string_branch(app, mocker) -> None:  # type: ignore[no-untyped-def]
    mocker.patch("hushline.crypto.Cert.from_bytes", return_value=object())
    mocker.patch("hushline.crypto.encrypt", return_value="cipher-text")
    with app.app_context():
        assert crypto.encrypt_message("msg", "pgp-key") == "cipher-text"


def test_stripe_invoice_remaining_paths(user: User) -> None:
    invoice_no_user = SimpleNamespace(
        id="inv_no_user",
        customer="cus_missing",
        hosted_invoice_url="https://example.com/inv0",
        total=10,
        status="open",
        created=None,
        lines=SimpleNamespace(data=[SimpleNamespace(plan=SimpleNamespace(product="prod_missing"))]),
    )
    with pytest.raises(ValueError, match="Could not find user"):
        StripeInvoice(invoice_no_user)  # type: ignore[arg-type]

    user.stripe_customer_id = "cus_ok"
    db.session.commit()
    business_tier = Tier.business_tier()
    assert business_tier is not None

    invoice_ok = SimpleNamespace(
        id="inv_ok",
        customer="cus_ok",
        hosted_invoice_url="https://example.com/inv",
        total=0,
        status="open",
        created=None,
        lines=SimpleNamespace(
            data=[SimpleNamespace(plan=SimpleNamespace(product=business_tier.stripe_product_id))]
        ),
    )
    invoice = StripeInvoice(invoice_ok)  # type: ignore[arg-type]
    assert invoice.total == 0

    invoice_missing_tier = SimpleNamespace(
        id="inv_missing_tier",
        customer="cus_ok",
        hosted_invoice_url="https://example.com/inv2",
        total=10,
        status="open",
        created=None,
        lines=SimpleNamespace(data=[SimpleNamespace(plan=SimpleNamespace(product="prod_missing"))]),
    )
    with pytest.raises(ValueError, match="Could not find tier"):
        StripeInvoice(invoice_missing_tier)  # type: ignore[arg-type]

    invoice_no_plan = SimpleNamespace(
        id="inv_no_plan",
        customer="cus_ok",
        hosted_invoice_url="https://example.com/inv3",
        total=10,
        status="open",
        created=None,
        lines=SimpleNamespace(data=[SimpleNamespace(plan=None)]),
    )
    with pytest.raises(ValueError, match="does not have a plan"):
        StripeInvoice(invoice_no_plan)  # type: ignore[arg-type]


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_route_delete_button_path(client: FlaskClient, user_alias) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data={DeleteAliasForm.submit.name: ""},
        follow_redirects=False,
    )
    assert response.status_code == 302


@pytest.mark.usefixtures("_authenticated_admin")
def test_branding_delete_logo_multirow_safety(client: FlaskClient, mocker) -> None:  # type: ignore[no-untyped-def]
    mocker.patch(
        "hushline.settings.branding.db.session.execute",
        return_value=SimpleNamespace(rowcount=2),
    )
    response = client.post(
        url_for("settings.branding"),
        data={DeleteBrandLogoForm.submit.name: ""},
        follow_redirects=False,
    )
    assert response.status_code == 503


@pytest.mark.usefixtures("_authenticated_admin")
def test_guidance_none_prompts_default_path(client: FlaskClient) -> None:
    with patch("hushline.settings.guidance.OrganizationSetting.fetch_one", return_value=None):
        response = client.get(url_for("settings.guidance"))
        assert response.status_code == 200


def test_settings_common_remaining_paths(app, user: User) -> None:  # type: ignore[no-untyped-def]
    fake_link_local_ip = SimpleNamespace(
        is_unspecified=False,
        is_loopback=False,
        is_private=False,
        is_link_local=True,
        is_multicast=False,
    )
    assert _is_blocked_ip(fake_link_local_ip) is True  # type: ignore[arg-type]

    async def _run() -> None:
        with app.app_context():
            app.config["TESTING"] = False
            assert await _is_safe_verification_url("https://8.8.8.8") is True
            with patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                return_value=[
                    (0, 0, 0, "", ("not-an-ip", 0)),
                    (0, 0, 0, "", ("8.8.8.8", 0)),
                ],
            ):
                assert await _is_safe_verification_url("https://example.com") is True

    asyncio.run(_run())

    with (
        app.test_request_context("/settings/fields", method="POST", data={"bogus": ""}),
        patch(
            "hushline.settings.common.FieldForm",
            return_value=SimpleNamespace(
                validate=lambda: True,
                submit=SimpleNamespace(name="submit"),
                update=SimpleNamespace(name="update"),
                delete=SimpleNamespace(name="delete"),
                move_up=SimpleNamespace(name="move_up"),
                move_down=SimpleNamespace(name="move_down"),
                id=SimpleNamespace(data="1"),
                label=SimpleNamespace(data="x"),
                field_type=SimpleNamespace(data=FieldType.TEXT.value),
                required=SimpleNamespace(data=False),
                enabled=SimpleNamespace(data=True),
                encrypted=SimpleNamespace(data=False),
                choices=SimpleNamespace(data=[]),
            ),
        ),
    ):
        assert handle_field_post(user.primary_username) is None


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_2fa_invalid_code_path(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("settings.enable_2fa"), follow_redirects=False)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        secret = sess["temp_totp_secret"]
    bad_code = "000000"
    assert bad_code != secret[:6]
    response = client.post(
        url_for("settings.enable_2fa"),
        data={"verification_code": bad_code},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.enable_2fa"))


@pytest.mark.asyncio()
async def test_worker_no_pending_event_hits_continue(app, mocker) -> None:  # type: ignore[no-untyped-def]
    import sqlalchemy as sa

    fake_engine = object()
    mocker.patch("hushline.premium.sa.create_engine", return_value=fake_engine)
    insp = SimpleNamespace(has_table=lambda _name: True)
    real_inspect = sa.inspect
    mocker.patch(
        "hushline.premium.sa.inspect",
        side_effect=lambda obj: insp if obj is fake_engine else real_inspect(obj),
    )

    call_count = {"n": 0}

    async def _stop(_seconds: int) -> None:
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise RuntimeError("stop-no-event")

    mocker.patch("hushline.premium.asyncio.sleep", side_effect=_stop)
    with pytest.raises(RuntimeError, match="stop-no-event"):
        await worker(app)
