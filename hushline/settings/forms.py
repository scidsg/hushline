import re
from typing import Any, Optional

from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, FileSize
from wtforms import (
    BooleanField,
    FormField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length
from wtforms.validators import Optional as OptionalField

from ..forms import CanonicalHTML, ComplexPassword, HexColor
from ..model import SMTPEncryption


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("Old Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )


class ChangeUsernameForm(FlaskForm):
    new_username = StringField("New Username", validators=[DataRequired(), Length(min=4, max=25)])


class SMTPSettingsForm(FlaskForm):
    class Meta:
        csrf = False

    smtp_server = StringField("SMTP Server", validators=[OptionalField(), Length(max=255)])
    smtp_port = IntegerField("SMTP Port", validators=[OptionalField()])
    smtp_username = StringField("SMTP Username", validators=[OptionalField(), Length(max=255)])
    smtp_password = PasswordField("SMTP Password", validators=[OptionalField(), Length(max=255)])
    smtp_encryption = SelectField(
        "SMTP Encryption Protocol", choices=[proto.value for proto in SMTPEncryption]
    )
    smtp_sender = StringField("SMTP Sender Address", validators=[Length(max=255)])


class EmailForwardingForm(FlaskForm):
    forwarding_enabled = BooleanField("Enable Forwarding", validators=[OptionalField()])
    email_address = StringField("Email Address", validators=[OptionalField(), Length(max=255)])
    custom_smtp_settings = BooleanField("Custom SMTP Settings", validators=[OptionalField()])
    smtp_settings = FormField(SMTPSettingsForm)

    def validate(self, extra_validators: list | None = None) -> bool:
        if not FlaskForm.validate(self, extra_validators):
            return False

        rv = True
        if self.forwarding_enabled.data:
            if not self.email_address.data:
                self.email_address.errors.append(
                    "Email address must be specified when forwarding is enabled."
                )
                rv = False
            if self.custom_smtp_settings.data or not current_app.config.get(
                "NOTIFICATIONS_ADDRESS"
            ):
                smtp_fields = [
                    self.smtp_settings.smtp_sender,
                    self.smtp_settings.smtp_username,
                    self.smtp_settings.smtp_server,
                    self.smtp_settings.smtp_port,
                ]
                unset_smtp_fields = [field for field in smtp_fields if not field.data]

                def remove_tags(text: str) -> str:
                    return re.sub("<[^<]+?>", "", text)

                for field in unset_smtp_fields:
                    field.errors.append(
                        f"{remove_tags(field.label())} is"
                        " required if custom SMTP settings are enabled."
                    )
                    rv = False
        return rv

    def flattened_errors(self, input: Optional[dict | list] = None) -> list[str]:
        errors = input if input else self.errors
        if isinstance(errors, list):
            return errors
        ret = []
        if isinstance(errors, dict):
            for error in errors.values():
                ret.extend(self.flattened_errors(error))
        return ret


class PGPProtonForm(FlaskForm):
    email = StringField(
        "",
        validators=[DataRequired(), Email()],
        render_kw={
            "placeholder": "Search Proton email...",
            "id": "proton_email",
            "required": True,
        },
    )


class PGPKeyForm(FlaskForm):
    pgp_key = TextAreaField("Or, Add Your Public PGP Key Manually", validators=[Length(max=100000)])


class DisplayNameForm(FlaskForm):
    display_name = StringField("Display Name", validators=[Length(max=100)])


class NewAliasForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=4, max=25)])


class DirectoryVisibilityForm(FlaskForm):
    show_in_directory = BooleanField("Show on public directory")


def strip_whitespace(value: Optional[Any]) -> Optional[str]:
    if value is not None and hasattr(value, "strip"):
        return value.strip()
    return value


class ProfileForm(FlaskForm):
    bio = TextAreaField("Bio", filters=[strip_whitespace], validators=[Length(max=250)])
    extra_field_label1 = StringField(
        "Extra Field Label 1",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value1 = StringField(
        "Extra Field Value 1",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    extra_field_label2 = StringField(
        "Extra Field Label 2",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value2 = StringField(
        "Extra Field Value 2",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    extra_field_label3 = StringField(
        "Extra Field Label 3",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value3 = StringField(
        "Extra Field Value 3",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    extra_field_label4 = StringField(
        "Extra Field Label 4",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value4 = StringField(
        "Extra Field Value 4",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )


class UpdateBrandPrimaryColorForm(FlaskForm):
    brand_primary_hex_color = StringField("Hex Color", validators=[DataRequired(), HexColor()])


class UpdateBrandAppNameForm(FlaskForm):
    brand_app_name = StringField(
        "App Name", validators=[CanonicalHTML(), DataRequired(), Length(min=2, max=30)]
    )


class UpdateBrandLogoForm(FlaskForm):
    logo = FileField(
        "Logo (.png only)",
        validators=[
            FileRequired(),
            FileAllowed(["png"], "Only PNG files are allowed"),
            FileSize(256 * 1000),  # 256 KB
        ],
    )
