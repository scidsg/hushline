import asyncio
import ipaddress
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from hushline.db import db
from hushline.model import FieldDefinition, FieldType, FieldValue, Message, User, Username
from hushline.settings.common import (
    _is_blocked_ip,
    _is_safe_verification_url,
    build_field_forms,
    handle_change_password_form,
    handle_field_post,
    handle_new_alias_form,
    handle_pgp_key_form,
    handle_profile_post,
    handle_update_bio,
    set_field_attribute,
    set_input_disabled,
    unset_field_attribute,
    verify_url,
)
from hushline.settings.forms import (
    ChangePasswordForm,
    DirectoryVisibilityForm,
    DisplayNameForm,
    NewAliasForm,
    PGPKeyForm,
    ProfileForm,
)


def test_set_and_unset_field_attribute(app: Flask) -> None:
    with app.app_context():
        form = DisplayNameForm()
        field = form.display_name

        assert field.render_kw is None
        set_field_attribute(field, "aria-label", "Display name")
        assert field.render_kw is not None
        assert field.render_kw["aria-label"] == "Display name"

        unset_field_attribute(field, "aria-label")
        assert field.render_kw is not None
        assert "aria-label" not in field.render_kw


def test_set_input_disabled_toggle(app: Flask) -> None:
    with app.app_context():
        form = DisplayNameForm()
        field = form.display_name

        set_input_disabled(field, True)
        assert field.render_kw is not None
        assert field.render_kw.get("disabled") == "disabled"

        set_input_disabled(field, False)
        assert field.render_kw is not None
        assert "disabled" not in field.render_kw


def test_is_blocked_ip_classification() -> None:
    assert _is_blocked_ip(ipaddress.IPv4Address(0)) is True
    assert _is_blocked_ip(ipaddress.ip_address("127.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("10.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("169.254.1.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("224.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("8.8.8.8")) is False


@pytest.mark.asyncio()
async def test_is_safe_verification_url_non_https_rejected_in_production(app: Flask) -> None:
    with app.app_context():
        app.config["TESTING"] = False
        assert await _is_safe_verification_url("http://example.com") is False


@pytest.mark.asyncio()
async def test_is_safe_verification_url_missing_hostname_rejected(app: Flask) -> None:
    with app.app_context():
        app.config["TESTING"] = False
        assert await _is_safe_verification_url("https:///foo") is False


@pytest.mark.asyncio()
async def test_is_safe_verification_url_testing_short_circuit(app: Flask) -> None:
    with app.app_context():
        app.config["TESTING"] = True
        assert await _is_safe_verification_url("http://example.com") is True


@pytest.mark.asyncio()
async def test_is_safe_verification_url_dns_error_rejected(app: Flask) -> None:
    with app.app_context():
        app.config["TESTING"] = False
        with patch.object(
            asyncio.get_running_loop(), "getaddrinfo", side_effect=OSError("dns fail")
        ):
            assert await _is_safe_verification_url("https://example.com") is False


@pytest.mark.asyncio()
async def test_is_safe_verification_url_resolved_private_rejected(app: Flask) -> None:
    with app.app_context():
        app.config["TESTING"] = False
        with patch.object(
            asyncio.get_running_loop(),
            "getaddrinfo",
            return_value=[(0, 0, 0, "", ("10.0.0.1", 0))],
        ):
            assert await _is_safe_verification_url("https://example.com") is False


@pytest.mark.asyncio()
async def test_is_safe_verification_url_resolved_public_allowed(app: Flask) -> None:
    with app.app_context():
        app.config["TESTING"] = False
        with patch.object(
            asyncio.get_running_loop(),
            "getaddrinfo",
            return_value=[(0, 0, 0, "", ("8.8.8.8", 0))],
        ):
            assert await _is_safe_verification_url("https://example.com") is True


@pytest.mark.asyncio()
async def test_verify_url_handles_client_error(user: User) -> None:
    username = user.primary_username
    profile_url = "https://example.com/profile"

    class _FailingResponse:
        def raise_for_status(self) -> None:
            raise aiohttp.ClientError("boom")

        async def text(self) -> str:
            return ""

    class _FailingContext:
        async def __aenter__(self) -> _FailingResponse:
            return _FailingResponse()

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            _ = (exc_type, exc, tb)

    class _Session:
        def get(self, url: str, timeout: aiohttp.ClientTimeout) -> _FailingContext:
            _ = (url, timeout)
            return _FailingContext()

    with patch("hushline.settings.common._is_safe_verification_url", return_value=True):
        await verify_url(_Session(), username, 1, "https://example.com", profile_url)  # type: ignore[arg-type]

    db.session.refresh(username)
    assert username.extra_field_verified1 is False


@pytest.mark.asyncio()
async def test_verify_url_marks_field_verified_when_profile_link_present(user: User) -> None:
    username = user.primary_username
    profile_url = "https://example.com/profile"

    class _SuccessResponse:
        def raise_for_status(self) -> None:
            return None

        async def text(self) -> str:
            return (
                '<html><body><a href="https://example.com/profile" '
                'rel="me">Profile</a></body></html>'
            )

    class _SuccessContext:
        async def __aenter__(self) -> _SuccessResponse:
            return _SuccessResponse()

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            _ = (exc_type, exc, tb)

    class _Session:
        def get(self, url: str, timeout: aiohttp.ClientTimeout) -> _SuccessContext:
            _ = (url, timeout)
            return _SuccessContext()

    with patch("hushline.settings.common._is_safe_verification_url", return_value=True):
        await verify_url(_Session(), username, 1, "https://example.com", profile_url)  # type: ignore[arg-type]

    assert username.extra_field_verified1 is True


@pytest.mark.asyncio()
async def test_verify_url_leaves_field_unverified_when_no_matching_profile_link(user: User) -> None:
    username = user.primary_username
    profile_url = "https://example.com/profile"

    class _SuccessResponse:
        def raise_for_status(self) -> None:
            return None

        async def text(self) -> str:
            return (
                '<html><body><a href="https://elsewhere.example" '
                'rel="nofollow">Other</a></body></html>'
            )

    class _SuccessContext:
        async def __aenter__(self) -> _SuccessResponse:
            return _SuccessResponse()

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            _ = (exc_type, exc, tb)

    class _Session:
        def get(self, url: str, timeout: aiohttp.ClientTimeout) -> _SuccessContext:
            _ = (url, timeout)
            return _SuccessContext()

    with patch("hushline.settings.common._is_safe_verification_url", return_value=True):
        await verify_url(_Session(), username, 1, "https://example.com", profile_url)  # type: ignore[arg-type]

    assert username.extra_field_verified1 is False


@pytest.mark.asyncio()
async def test_handle_update_bio_reraises_task_exceptions_in_testing(
    app: Flask, user: User
) -> None:
    username = user.primary_username
    with app.test_request_context("/settings/profile", method="POST"):
        form = ProfileForm()
        form.bio.data = "bio"
        form.extra_field_value1.data = "http://example.com"
        form.extra_field_label1.data = "site"
        for i in range(2, 5):
            getattr(form, f"extra_field_value{i}").data = ""
            getattr(form, f"extra_field_label{i}").data = ""

        with (
            patch(
                "hushline.settings.common.verify_url",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await handle_update_bio(username, form)


@pytest.mark.asyncio()
async def test_handle_update_bio_logs_task_exceptions_when_not_testing(
    app: Flask, user: User
) -> None:
    username = user.primary_username
    with app.test_request_context("/settings/profile", method="POST"):
        app.config["TESTING"] = False
        form = ProfileForm()
        form.bio.data = "bio"
        form.extra_field_value1.data = "https://example.com"
        form.extra_field_label1.data = "site"
        for i in range(2, 5):
            getattr(form, f"extra_field_value{i}").data = ""
            getattr(form, f"extra_field_label{i}").data = ""

        with (
            patch(
                "hushline.settings.common.verify_url",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(app.logger, "warning") as warning_log,
        ):
            response = await handle_update_bio(username, form)

        assert response.status_code == 302
        warning_log.assert_called()


def test_handle_new_alias_form_unique_violation_returns_none(
    app: Flask, user: User, user_alias: Username
) -> None:
    _ = user_alias
    user.set_business_tier()
    db.session.commit()
    form = NewAliasForm(data={"username": "new-alias"})

    with (
        app.test_request_context("/settings/aliases", method="POST"),
        patch(
            "hushline.settings.common.db.session.commit",
            side_effect=IntegrityError(
                "stmt",
                "params",
                Exception('duplicate key value violates unique constraint "uq_usernames_username"'),
            ),
        ),
        patch("hushline.settings.common.UniqueViolation", Exception),
    ):
        result = handle_new_alias_form(user, form)

    assert result is None


def test_handle_new_alias_form_integrity_error_returns_none(app: Flask, user: User) -> None:
    user.set_business_tier()
    db.session.commit()
    form = NewAliasForm(data={"username": "new-alias-2"})

    with (
        app.test_request_context("/settings/aliases", method="POST"),
        patch(
            "hushline.settings.common.db.session.commit",
            side_effect=IntegrityError("stmt", "params", Exception("other error")),
        ),
    ):
        result = handle_new_alias_form(user, form)

    assert result is None


def test_handle_change_password_form_rejects_wrong_old_password(
    app: Flask, user: User, user_password: str
) -> None:
    with app.test_request_context("/settings/auth", method="POST"):
        form = cast(
            ChangePasswordForm,
            SimpleNamespace(
                old_password=SimpleNamespace(data="wrong-password", errors=[]),
                new_password=SimpleNamespace(data=user_password + "x", errors=[]),
            ),
        )
        result = handle_change_password_form(user, form)

    assert result is None
    assert "Incorrect old password." in form.old_password.errors


def test_handle_pgp_key_form_empty_value_clears_key_and_email(app: Flask, user: User) -> None:
    user.pgp_key = "dummy"
    user.email = "test@example.com"
    db.session.commit()

    with app.test_request_context("/settings/encryption", method="POST"):
        form = PGPKeyForm(data={"pgp_key": ""})
        response = handle_pgp_key_form(user, form)

    assert response.status_code == 302
    db.session.refresh(user)
    assert user.pgp_key is None
    assert user.email is None


@pytest.mark.asyncio()
async def test_handle_profile_post_invalid_form_returns_none(app: Flask, user: User) -> None:
    username = user.primary_username
    with app.test_request_context("/settings/profile", method="POST", data={}):
        display_name_form = DisplayNameForm(data={"display_name": username.display_name or "X"})
        directory_form = cast(
            DirectoryVisibilityForm,
            SimpleNamespace(
                submit=SimpleNamespace(name="directory_submit"), validate=lambda: False
            ),
        )
        profile_form = ProfileForm()
        result = await handle_profile_post(
            display_name_form, directory_form, profile_form, username
        )  # type: ignore[arg-type]
        assert result is None


def _fake_field_form(action: str, field_id: int | None = None) -> SimpleNamespace:
    submit = SimpleNamespace(name="submit")
    update = SimpleNamespace(name="update")
    delete = SimpleNamespace(name="delete")
    move_up = SimpleNamespace(name="move_up")
    move_down = SimpleNamespace(name="move_down")
    return SimpleNamespace(
        validate=lambda: True,
        submit=submit,
        update=update,
        delete=delete,
        move_up=move_up,
        move_down=move_down,
        id=SimpleNamespace(data=str(field_id or 0)),
        label=SimpleNamespace(data=f"label-{action}"),
        field_type=SimpleNamespace(data=FieldType.TEXT.value),
        required=SimpleNamespace(data=False),
        enabled=SimpleNamespace(data=True),
        encrypted=SimpleNamespace(data=False),
        choices=SimpleNamespace(data=[{"choice": "a"}, {"choice": "b"}]),
    )


def test_handle_field_post_add_branch(app: Flask, user: User) -> None:
    username = user.primary_username
    with (
        app.test_request_context("/settings/fields", method="POST", data={"submit": ""}),
        patch("hushline.settings.common.FieldForm", return_value=_fake_field_form("add")),
        patch(
            "hushline.settings.common.redirect_to_self",
            return_value=SimpleNamespace(status_code=302),
        ),
    ):
        response = handle_field_post(username)
    assert response is not None
    assert db.session.scalar(db.select(FieldDefinition).filter_by(label="label-add")) is not None


def test_handle_field_post_update_branch(app: Flask, user: User) -> None:
    username = user.primary_username
    field = FieldDefinition(
        username=username,
        label="before",
        field_type=FieldType.TEXT,
        required=False,
        enabled=True,
        encrypted=False,
        choices=[],
    )
    db.session.add(field)
    db.session.commit()

    with (
        app.test_request_context("/settings/fields", method="POST", data={"update": ""}),
        patch(
            "hushline.settings.common.FieldForm",
            return_value=_fake_field_form("update", field.id),
        ),
        patch(
            "hushline.settings.common.redirect_to_self",
            return_value=SimpleNamespace(status_code=302),
        ),
    ):
        response = handle_field_post(username)
    assert response is not None
    db.session.refresh(field)
    assert field.label == "label-update"


def test_handle_field_post_delete_branch(app: Flask, user: User) -> None:
    username = user.primary_username
    field = FieldDefinition(
        username=username,
        label="delete-me",
        field_type=FieldType.TEXT,
        required=False,
        enabled=True,
        encrypted=False,
        choices=[],
    )
    db.session.add(field)
    db.session.commit()
    message = Message(username_id=username.id)
    db.session.add(message)
    db.session.commit()
    value = FieldValue(field_definition=field, message=message, value="v", encrypted=False)
    db.session.add(value)
    db.session.commit()

    with (
        app.test_request_context("/settings/fields", method="POST", data={"delete": ""}),
        patch(
            "hushline.settings.common.FieldForm",
            return_value=_fake_field_form("delete", field.id),
        ),
        patch(
            "hushline.settings.common.redirect_to_self",
            return_value=SimpleNamespace(status_code=302),
        ),
    ):
        response = handle_field_post(username)
    assert response is not None
    assert db.session.get(FieldDefinition, field.id) is None


def test_handle_field_post_move_up_and_down_branches(app: Flask, user: User) -> None:
    username = user.primary_username
    first = FieldDefinition(
        username=username,
        label="first",
        field_type=FieldType.TEXT,
        required=False,
        enabled=True,
        encrypted=False,
        choices=[],
    )
    second = FieldDefinition(
        username=username,
        label="second",
        field_type=FieldType.TEXT,
        required=False,
        enabled=True,
        encrypted=False,
        choices=[],
    )
    db.session.add(first)
    db.session.commit()
    second.sort_order = first.sort_order + 1
    db.session.add(second)
    db.session.commit()

    with (
        app.test_request_context("/settings/fields", method="POST", data={"move_up": ""}),
        patch(
            "hushline.settings.common.FieldForm",
            return_value=_fake_field_form("up", second.id),
        ),
        patch(
            "hushline.settings.common.redirect_to_self",
            return_value=SimpleNamespace(status_code=302),
        ),
    ):
        response_up = handle_field_post(username)
    assert response_up is not None

    with (
        app.test_request_context("/settings/fields", method="POST", data={"move_down": ""}),
        patch(
            "hushline.settings.common.FieldForm",
            return_value=_fake_field_form("down", second.id),
        ),
        patch(
            "hushline.settings.common.redirect_to_self",
            return_value=SimpleNamespace(status_code=302),
        ),
    ):
        response_down = handle_field_post(username)
    assert response_down is not None


def test_build_field_forms_populates_choice_entries(user: User) -> None:
    username = user.primary_username
    field = FieldDefinition(
        username=username,
        label="with-choices",
        field_type=FieldType.CHOICE_SINGLE,
        required=False,
        enabled=True,
        encrypted=False,
        choices=["x", "y"],
    )
    db.session.add(field)
    db.session.commit()

    field_forms, new_field_form = build_field_forms(username)
    assert len(field_forms) > 0
    assert field_forms[-1].choices.entries[0].choice.data == "x"
    assert field_forms[-1].choices.entries[1].choice.data == "y"
    assert new_field_form is not None
