import re
from typing import Any, Optional

from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import (
    BooleanField,
    Field,
    FieldList,
    Form,
    FormField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    URL,
    AnyOf,
    DataRequired,
    Email,
    Length,
    ValidationError,
)
from wtforms.validators import Optional as OptionalField

from hushline.db import db
from hushline.forms import Button, CanonicalHTML, ComplexPassword, HexColor, ValidTemplate
from hushline.model import FieldType, MessageStatus, SMTPEncryption, Username
from hushline.routes.common import valid_username


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
    new_username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=Username.USERNAME_MIN_LENGTH, max=Username.USERNAME_MAX_LENGTH),
        ],
    )
    submit = SubmitField("Change Username", name="update_display_name", widget=Button())


class DataExportForm(FlaskForm):
    encrypt_export = BooleanField("Encrypt export with my PGP key", default=True)
    submit = SubmitField("Download My Data", name="download_data", widget=Button())


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
    display_name = StringField(
        "Display Name",
        validators=[
            OptionalField(),
            Length(min=Username.DISPLAY_NAME_MIN_LENGTH, max=Username.DISPLAY_NAME_MAX_LENGTH),
        ],
    )
    submit = SubmitField("Update Display Name", name="update_display_name", widget=Button())


class NewAliasForm(FlaskForm):
    username = StringField(
        "Alias Username",
        validators=[
            DataRequired(),
            Length(min=Username.USERNAME_MIN_LENGTH, max=Username.USERNAME_MAX_LENGTH),
            valid_username,
        ],
    )
    submit = SubmitField("Add Alias", name="new_alias", widget=Button())


class DeleteAliasForm(FlaskForm):
    submit = SubmitField("Delete Alias", name="delete_alias", widget=Button())


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


class UserGuidancePromptContentForm(FlaskForm):
    heading_text = StringField("Prompt Heading", validators=[Length(min=0, max=50)])
    prompt_text = TextAreaField("Prompt Text", validators=[Length(min=0, max=1024)])
    submit = SubmitField("Update", name="update_prompt", widget=Button())
    delete_submit = SubmitField("Delete This Prompt", name="delete_prompt", widget=Button())


class UserGuidanceAddPromptForm(FlaskForm):
    submit = SubmitField("Add New Prompt", name="add_prompt", widget=Button())


class SetMessageStatusTextForm(FlaskForm):
    markdown = TextAreaField("Status Text", validators=[OptionalField()])
    # WTForms errors on SelectField(..., widget=HiddenInput()), so we have this instead
    status = HiddenField(validators=[DataRequired(), AnyOf([x.value for x in MessageStatus])])
    submit = SubmitField("Update Reply Text", widget=Button())


class UpdateDirectoryTextForm(FlaskForm):
    markdown = TextAreaField("Directory Intro Text", validators=[DataRequired()])
    submit = SubmitField("Update Text", name="update_directory_text", widget=Button())


class SetHomepageUsernameForm(FlaskForm):
    username = StringField(validators=[DataRequired()])
    submit = SubmitField("Set Username", name="set_homepage_user", widget=Button())
    delete_submit = SubmitField("Reset", name="delete_homepage_user", widget=Button())

    def validate_username(self, field: Field) -> None:
        username = field.data.strip()
        if not db.session.scalar(
            db.exists(Username).where(Username._username == username).select()
        ):
            raise ValidationError(f"Username {username!r} does not exist")


class UpdateProfileHeaderForm(FlaskForm):
    template = StringField(
        "Custom Profile Header",
        validators=[
            OptionalField(),
            Length(max=500),
            ValidTemplate(
                {
                    "display_name_or_username": "x",
                    "display_name": "x",
                    "username": "x",
                }
            ),
        ],
    )
    submit = SubmitField("Update Profile Header", name="update_profile_header", widget=Button())


class FieldChoiceForm(Form):
    choice = StringField("Choice", validators=[DataRequired()])


class FieldForm(FlaskForm):
    id = HiddenField()
    label = StringField("Label", validators=[DataRequired(), Length(max=500)])
    field_type = SelectField(
        "Field Type",
        choices=[(field_type.value, field_type.label()) for field_type in FieldType],
        validators=[DataRequired()],
    )
    choices = FieldList(FormField(FieldChoiceForm), validators=[OptionalField()], default=[])
    encrypted = BooleanField("Encrypted", default=True)
    required = BooleanField("Required", default=True)
    enabled = BooleanField("Enabled", default=True)

    submit = SubmitField("Add Field", name="add_field", widget=Button())
    update = SubmitField("Update Field", name="update_field", widget=Button())
    delete = SubmitField(
        "Delete Field",
        name="delete_field",
        widget=Button(),
        render_kw={"class": "btn-danger message-field-delete-button"},
    )
    move_up = SubmitField("Move Field Up", name="move_up", widget=Button())
    move_down = SubmitField("Move Field Down", name="move_down", widget=Button())
