from wtforms.validators import Length

from hushline.routes.forms import LoginForm, RegistrationForm


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
