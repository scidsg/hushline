from flask_wtf import FlaskForm
from wtforms import PasswordField, RadioField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from hushline.forms import ComplexPassword
from hushline.model import FieldDefinition, FieldType
from hushline.routes.common import valid_username


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])


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


class MessageForm(FlaskForm):
    contact_method = StringField(
        "Contact Method",
        validators=[Optional(), Length(max=255)],  # Optional if you want it to be non-mandatory
    )
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
    )


class CustomMessageBaseForm(FlaskForm):
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
    )


class CustomMessageForm:
    def __init__(self, fields: list[FieldDefinition]):
        # Create a custom form class for this instance of CustomMessageForm
        class F(CustomMessageBaseForm):
            pass

        self.F = F

        # Add the fields to the form
        for i, field in enumerate(fields):
            # Skip disabled fields
            if not field.enabled:
                continue

            validators = []

            # Required or optional
            if field.required:
                validators.append(DataRequired())
            else:
                validators.append(Optional())

            # Multiline text has 10000 chars, all other types (types, single choice, and multiple
            # choice) have 255 chars
            if field.field_type == FieldType.MULTILINE_TEXT:
                validators.append(Length(max=10000))
            else:
                validators.append(Length(max=255))

            # Add the field to the form
            if field.field_type == FieldType.TEXT:
                setattr(
                    self.F, f"field_{field.id}", StringField(field.label, validators=validators)
                )
            elif field.field_type == FieldType.MULTILINE_TEXT:
                setattr(
                    self.F, f"field_{field.id}", TextAreaField(field.label, validators=validators)
                )
            elif field.field_type == FieldType.CHOICE_SINGLE:
                setattr(
                    self.F,
                    f"field_{field.id}",
                    RadioField(
                        field.label, choices=field.choices, validators=validators, coerce=str
                    ),
                )
            elif field.field_type == FieldType.CHOICE_MULTIPLE:
                setattr(
                    self.F,
                    f"field_{field.id}",
                    SelectField(
                        field.label, choices=field.choices, validators=validators, coerce=str
                    ),
                )
            else:
                raise ValueError(f"Unknown field type: {field.field_type}")
