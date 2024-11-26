import re
from typing import Any, Optional

from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from markupsafe import Markup
from wtforms import (
    BooleanField,
    Field,
    FormField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import URL, DataRequired, Email, Length
from wtforms.validators import Optional as OptionalField
from wtforms.widgets.core import html_params

from ..forms import CanonicalHTML, ComplexPassword, HexColor
from ..model import SMTPEncryption


class Button:
    html_params = staticmethod(html_params)

    def __call__(self, field: Field, **kwargs: Any) -> Markup:
        kwargs.setdefault("id", field.id)
        kwargs.setdefault("type", "submit")
        kwargs.setdefault("value", field.label.text)
        if "value" not in kwargs:
            kwargs["value"] = field._value()
        if "required" not in kwargs and "required" in getattr(field, "flags", []):
            kwargs["required"] = True
        params = self.html_params(name=field.name, **kwargs)
        return Markup(f"<button {params}>{kwargs['value']}</button>")


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
    submit = SubmitField("Change Password", name="change_password", widget=Button())


class ChangeUsernameForm(FlaskForm):
    new_username = StringField("Username", validators=[DataRequired(), Length(min=4, max=25)])
    submit = SubmitField("Change Username", name="update_display_name", widget=Button())


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
    submit = SubmitField("Update Email Forwarding", name="update_email_forwarding", widget=Button())

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
    submit = SubmitField("Update PGP Key", name="update_pgp_key", widget=Button())


class DisplayNameForm(FlaskForm):
    display_name = StringField("Display Name", validators=[OptionalField(), Length(max=100)])
    submit = SubmitField("Update Display Name", name="update_display_name", widget=Button())


class NewAliasForm(FlaskForm):
    username = StringField("Alias Username", validators=[DataRequired(), Length(min=4, max=25)])
    submit = SubmitField("Add Alias", name="new_alias", widget=Button())


class DirectoryVisibilityForm(FlaskForm):
    show_in_directory = BooleanField("Show on public directory")
    submit = SubmitField("Update Visibilty", name="update_directory_visibility", widget=Button())


def strip_whitespace(value: Optional[Any]) -> Optional[str]:
    if value is not None and hasattr(value, "strip"):
        return value.strip()
    return value


class ProfileForm(FlaskForm):
    bio = TextAreaField("Bio", filters=[strip_whitespace], validators=[Length(max=250)])
    extra_field_label1 = StringField(
        "Label",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value1 = StringField(
        "Content",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    extra_field_label2 = StringField(
        "Label",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value2 = StringField(
        "Content",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    extra_field_label3 = StringField(
        "Label",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value3 = StringField(
        "Content",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    extra_field_label4 = StringField(
        "Label",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=50)],
    )
    extra_field_value4 = StringField(
        "Content",
        filters=[strip_whitespace],
        validators=[OptionalField(), Length(max=4096)],
    )
    submit = SubmitField("Update Bio", name="update_bio", widget=Button())


class UpdateBrandPrimaryColorForm(FlaskForm):
    brand_primary_hex_color = StringField("Choose Color", validators=[DataRequired(), HexColor()])
    submit = SubmitField("Update Color", name="update_color", widget=Button())


class UpdateBrandAppNameForm(FlaskForm):
    brand_app_name = StringField(
        "App Name", validators=[CanonicalHTML(), DataRequired(), Length(min=2, max=30)]
    )
    submit = SubmitField("Update Name", name="update_name", widget=Button())


class UpdateBrandLogoForm(FlaskForm):
    logo = FileField(
        "Logo (.png only)",
        validators=[
            # NOTE: not present because the same form w/ 2 submit buttons is used for deletions
            # FileRequired()
            FileAllowed(["png"], "Only PNG files are allowed"),
            FileSize(256 * 1000),  # 256 KB
        ],
    )
    submit = SubmitField("Update Logo", name="update_logo", widget=Button())


class DeleteBrandLogoForm(FlaskForm):
    submit = SubmitField("Delete Logo", name="submit_logo", widget=Button())


class UserGuidanceForm(FlaskForm):
    show_user_guidance = BooleanField("Show user guidance")
    submit = SubmitField("Update User Guidance", name="update_user_guidance", widget=Button())


class UserGuidanceEmergencyExitForm(FlaskForm):
    exit_button_text = StringField(
        "Exit Button Text", validators=[DataRequired(), Length(min=1, max=50)]
    )
    exit_button_link = StringField(
        "Exit Button Link", validators=[DataRequired(), Length(min=1, max=2000), URL()]
    )
    submit = SubmitField("Update Exit Button", name="update_exit_button", widget=Button())
