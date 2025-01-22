from flask_wtf import FlaskForm
from wtforms import (
    PasswordField,
    RadioField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional
from wtforms.widgets import CheckboxInput, ListWidget

from hushline.forms import ComplexPassword
from hushline.model import FieldDefinition, FieldType
from hushline.routes.common import valid_username


# https://wtforms.readthedocs.io/en/3.2.x/specific_problems/#specialty-field-tricks
class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """

    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


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


class DynamicMessageForm:
    def __init__(self, fields: list[FieldDefinition]):
        self.fields = fields

        # Create a custom form class for this instance of CustomMessageForm
        class F(FlaskForm):
            pass

        self.F = F

        # If there are no fields, add the default contact method field
        if len(fields) == 0:
            setattr(
                self.F,
                "contact_method",
                StringField("Contact Method", validators=[Optional(), Length(max=255)]),
            )

        # Add the fields to the form
        for i, field in enumerate(fields):
            # Skip disabled fields
            if not field.enabled:
                continue

            # Define the validators
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
            name = f"field_{i}"
            if field.field_type == FieldType.TEXT:
                setattr(self.F, name, StringField(field.label, validators=validators))
            elif field.field_type == FieldType.MULTILINE_TEXT:
                setattr(self.F, name, TextAreaField(field.label, validators=validators))
            elif field.field_type == FieldType.CHOICE_SINGLE:
                # Decide if we want radio buttons or dropdown depending on the number of choices
                field_type = RadioField if len(field.choices) < 3 else SelectField  # noqa: PLR2004
                setattr(
                    self.F,
                    name,
                    field_type(
                        field.label, choices=field.choices, validators=validators, coerce=str
                    ),
                )
            elif field.field_type == FieldType.CHOICE_MULTIPLE:
                setattr(
                    self.F,
                    name,
                    MultiCheckboxField(
                        field.label, choices=field.choices, validators=validators, coerce=str
                    ),
                )
            else:
                raise ValueError(f"Unknown field type: {field.field_type}")

        # Add the message field at the end
        setattr(
            self.F,
            "content",
            TextAreaField("Message", validators=[DataRequired(), Length(max=10000)]),
        )

    def field_names(self) -> list[str]:
        """
        Return a list of field names for this form for the template to loop through
        """
        if len(self.fields) == 0:
            return ["contact_method", "content"]

        names = []
        for i in range(len(self.fields)):
            if self.fields[i].enabled:
                names.append(f"field_{i}")
        names.append("content")
        return names

    def form(self) -> FlaskForm:
        """
        Return an instance of the custom form class
        """
        return self.F()
