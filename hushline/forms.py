import html
import re

from flask_wtf import FlaskForm
from wtforms import Field, Form, StringField
from wtforms.validators import DataRequired, Length, ValidationError


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


class HexColor:
    # HTML input color elements only give & accept 6-hexit color codes
    hex_color_regex: re.Pattern = re.compile(r"^#[0-9a-fA-F]{6}$")

    def __call__(self, form: Form, field: Field) -> None:
        color: str = field.data
        if not self.hex_color_regex.match(color):
            raise ValidationError(f"{color=} is an invalid 6-hexit color code. (eg. #7d25c1)")


class CanonicalHTML:
    def __call__(self, form: Form, field: Field) -> None:
        text: str = field.data
        if text != html.escape(text).strip():
            raise ValidationError(f"{text=} is ambiguous or unescaped.")


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])
