from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from wtforms.validators import Length

from hushline.model import FieldType
from hushline.routes.forms import (
    ENCRYPTED_CHOICE_MAX_LENGTH,
    DynamicMessageForm,
    LoginForm,
    OnboardingProfileForm,
    RegistrationForm,
)


def _get_length_validator(form_class: type, field_name: str) -> Length | None:
    field = getattr(form_class, field_name)
    for validator in field.kwargs.get("validators", []):
        if isinstance(validator, Length):
            return validator
    return None


def test_login_password_max_matches_registration() -> None:
    login_length = _get_length_validator(LoginForm, "password")
    registration_length = _get_length_validator(RegistrationForm, "password")
    assert login_length is not None
    assert registration_length is not None
    assert login_length.max == registration_length.max


def test_login_username_max_matches_registration() -> None:
    login_length = _get_length_validator(LoginForm, "username")
    registration_length = _get_length_validator(RegistrationForm, "username")
    assert login_length is not None
    assert registration_length is not None
    assert login_length.max == registration_length.max


def test_dynamic_message_form_skips_disabled_fields_and_maps_names(app: Flask) -> None:
    fields = [
        SimpleNamespace(
            enabled=True,
            required=True,
            field_type=FieldType.TEXT,
            encrypted=False,
            label="Enabled",
            choices=[],
        ),
        SimpleNamespace(
            enabled=False,
            required=False,
            field_type=FieldType.TEXT,
            encrypted=False,
            label="Disabled",
            choices=[],
        ),
    ]
    dynamic = DynamicMessageForm(fields)  # type: ignore[arg-type]
    with app.test_request_context():
        form = dynamic.form()

    assert hasattr(form, "field_0")
    assert not hasattr(form, "field_1")
    assert hasattr(form, "encrypted_email_body")
    assert hasattr(form, "owner_guard_nonce")
    assert hasattr(form, "owner_guard_signature")
    assert hasattr(form, "captcha_answer")
    assert dynamic.field_from_name("field_0") is fields[0]
    assert dynamic.field_from_name("missing") is None
    assert dynamic.field_data()[1]["field"] is fields[1]


def test_dynamic_message_form_unknown_field_type_raises() -> None:
    bad_field = SimpleNamespace(
        enabled=True,
        required=False,
        field_type=object(),
        encrypted=False,
        label="Bad",
        choices=[],
    )
    with pytest.raises(ValueError, match="Unknown field type"):
        DynamicMessageForm([bad_field])  # type: ignore[list-item]


def test_dynamic_message_form_choice_fields_select_and_multicheckbox(app: Flask) -> None:
    fields = [
        SimpleNamespace(
            enabled=True,
            required=False,
            field_type=FieldType.CHOICE_SINGLE,
            encrypted=True,
            label="Single",
            choices=["a", "b", "c", "d"],
        ),
        SimpleNamespace(
            enabled=True,
            required=False,
            field_type=FieldType.CHOICE_MULTIPLE,
            encrypted=True,
            label="Multiple",
            choices=["x", "y"],
        ),
    ]
    dynamic = DynamicMessageForm(fields)  # type: ignore[arg-type]
    with app.test_request_context():
        form = dynamic.form()

    assert form.field_0.__class__.__name__ == "SelectField"
    assert form.field_1.__class__.__name__ == "MultiCheckboxField"

    skip_invalid_choice = next(
        validator
        for validator in form.field_0.validators
        if getattr(validator, "__name__", "") == "skip_invalid_choice"
    )
    form.field_0.errors = ["Not a valid choice.", "another"]
    skip_invalid_choice(form, form.field_0)
    assert form.field_0.errors == ["another"]


def test_dynamic_message_form_accepts_encrypted_choice_payloads(app: Flask) -> None:
    encrypted_payload = (
        "-----BEGIN PGP MESSAGE-----\n\n"
        "wV4DySYCvmcevcgSAQdAexampleencryptedpayload\n"
        "-----END PGP MESSAGE-----"
    )
    fields = [
        SimpleNamespace(
            enabled=True,
            required=False,
            field_type=FieldType.CHOICE_SINGLE,
            encrypted=True,
            label="Reason for reaching out",
            choices=[
                "Whistleblower Requests",
                "Founder Request",
                "Investor or Funder Inquiry",
            ],
        ),
        SimpleNamespace(
            enabled=True,
            required=False,
            field_type=FieldType.CHOICE_MULTIPLE,
            encrypted=True,
            label="Topics",
            choices=["Research", "Media"],
        ),
    ]
    dynamic = DynamicMessageForm(fields)  # type: ignore[arg-type]

    with app.test_request_context(
        method="POST",
        data={
            "field_0": encrypted_payload,
            "field_1": encrypted_payload,
        },
    ):
        form = dynamic.form(csrf_enabled=False)

        assert form.validate(), form.errors


def test_dynamic_message_form_rejects_invalid_encrypted_choice_values(app: Flask) -> None:
    oversized_pgp_payload = (
        "-----BEGIN PGP MESSAGE-----\n"
        + "a" * ENCRYPTED_CHOICE_MAX_LENGTH
        + "\n-----END PGP MESSAGE-----"
    )
    fields = [
        SimpleNamespace(
            enabled=True,
            required=False,
            field_type=FieldType.CHOICE_MULTIPLE,
            encrypted=True,
            label="Topics",
            choices=["Research", "Media"],
        ),
    ]
    dynamic = DynamicMessageForm(fields)  # type: ignore[arg-type]

    with app.test_request_context(
        method="POST",
        data={"field_0": "not-a-choice-or-pgp"},
    ):
        form = dynamic.form(csrf_enabled=False)

        assert not form.validate()
        assert "not a valid choice" in form.field_0.errors[0].lower()

    with app.test_request_context(
        method="POST",
        data={"field_0": oversized_pgp_payload},
    ):
        form = dynamic.form(csrf_enabled=False)

        assert not form.validate()
        assert "not a valid choice" in form.field_0.errors[0].lower()


def test_onboarding_profile_form_rejects_disallowed_language(app: Flask) -> None:
    def _mock_contains_disallowed_text(text: str | None) -> bool:
        return bool(text and "blocked-token" in text)

    with app.test_request_context(), patch(
        "hushline.forms.contains_disallowed_text",
        side_effect=_mock_contains_disallowed_text,
    ):
        form = OnboardingProfileForm(data={"display_name": "blocked-token", "bio": "clean bio"})
        assert not form.validate()
        assert form.display_name.errors

        form = OnboardingProfileForm(data={"display_name": "clean-name", "bio": "blocked-token"})
        assert not form.validate()
        assert form.bio.errors
