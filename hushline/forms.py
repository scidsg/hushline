import re

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length, ValidationError


class ComplexPassword(object):
    def __init__(self, message=None):
        if not message:
            message = (
                "⛔️ Password must include uppercase, lowercase, digit, and a special character."
            )
        self.message = message

    # TODO the regexes here should be fields in the class so they are compiled once
    def __call__(self, form, field):
        password = field.data
        if not (
            re.search("[A-Z]", password)
            and re.search("[a-z]", password)
            and re.search("[0-9]", password)
            and re.search("[^A-Za-z0-9]", password)
        ):
            raise ValidationError(self.message)


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])
