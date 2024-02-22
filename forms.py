from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length, Email, Regexp, ValidationError
import re

class ComplexPassword(object):
    """
    Custom validator for password complexity.
    Ensures passwords contain at least one uppercase letter, one lowercase letter, one digit, and one special character.
    """
    def __init__(self, message=None):
        if not message:
            message = "Password must include uppercase, lowercase, digit, and a special character."
        self.message = message

    def __call__(self, form, field):
        password = field.data
        if not (re.search("[A-Z]", password) and re.search("[a-z]", password) and re.search("[0-9]", password) and re.search("[^A-Za-z0-9]", password)):
            raise ValidationError(self.message)

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])

class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=4, max=25)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128), ComplexPassword()])
    invite_code = StringField("Invite Code", validators=[DataRequired(), Length(min=6, max=25)])

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("Old Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128), ComplexPassword()])

class ChangeUsernameForm(FlaskForm):
    new_username = StringField("New Username", validators=[DataRequired(), Length(min=4, max=25)])

class SMTPSettingsForm(FlaskForm):
    smtp_server = StringField("SMTP Server", validators=[DataRequired()])
    smtp_port = IntegerField("SMTP Port", validators=[DataRequired()])
    smtp_username = StringField("SMTP Username", validators=[DataRequired()])
    smtp_password = PasswordField("SMTP Password", validators=[DataRequired()])

class PGPKeyForm(FlaskForm):
    pgp_key = TextAreaField("PGP Key", validators=[Length(max=20000)])

class DisplayNameForm(FlaskForm):
    display_name = StringField("Display Name", validators=[Length(max=100)])

class MessageForm(FlaskForm):
    content = TextAreaField("Message", validators=[DataRequired(), Length(max=2000)], render_kw={"placeholder": "Include a contact method if you want a response..."})

class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])
