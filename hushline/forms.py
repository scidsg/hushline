import re
from hmac import compare_digest as bytes_are_equal
from typing import Callable

from flask_wtf import FlaskForm
from wtforms import Field, Form, StringField
from wtforms.validators import DataRequired, Length, ValidationError


class WrongPassword(ValueError):
    pass


class ComplexPassword:
    def __init__(self, message: str | None = None) -> None:
        if not message:
            message = (
                "⛔️ Password must include uppercase, lowercase, digit, and a special character."
            )
        self.message = message

    # TODO the regexes here should be fields in the class so they are compiled once
    def __call__(self, form: Form, field: Field) -> None:
        password = field.data
        if not (
            re.search("[A-Z]", password)
            and re.search("[a-z]", password)
            and re.search("[0-9]", password)
            and re.search("[^A-Za-z0-9]", password)
        ):
            raise ValidationError(self.message)


def is_valid_password_swap(
    *, check_password: Callable[[str], bool], old_password: str, new_password: str
) -> bool:
    # since the passwords can be of different lengths, the equality test must occur *iif*
    # the correctness test passes, since timing differences leak length information
    if check_password(old_password):
        return not bytes_are_equal(old_password.encode(), new_password.encode())
    raise WrongPassword


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])
