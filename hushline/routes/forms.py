from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from hushline.forms import ComplexPassword
from hushline.routes.common import valid_username


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])


class MessageForm(FlaskForm):
    contact_method = StringField(
        "Contact Method",
        validators=[Optional(), Length(max=255)],  # Optional if you want it to be non-mandatory
    )
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
    )


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=25), valid_username]
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )
    invite_code = StringField("Invite Code", validators=[DataRequired(), Length(min=6, max=25)])


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
