from flask import Flask
from flask_wtf import FlaskForm
from werkzeug.datastructures import MultiDict
from wtforms import FieldList, Form, FormField, StringField, SubmitField

from hushline.settings.forms import EmailForwardingForm, SetHomepageUsernameForm
from tests.helpers import form_to_data


class _ChoiceForm(Form):
    choice = StringField("Choice")


class _ChoiceListForm(FlaskForm):
    choices = FieldList(FormField(_ChoiceForm), min_entries=0)
    submit = SubmitField("Save", name="save")


def test_form_to_data_flattens_prefixed_subforms(app: Flask) -> None:
    with app.test_request_context():
        form = EmailForwardingForm(
            prefix="notifications",
            data={
                "email_address": "primary@example.com",
                "custom_smtp_settings": True,
                "smtp_settings": {
                    "smtp_server": "smtp.example.com",
                    "smtp_port": 587,
                    "smtp_username": "user@example.com",
                    "smtp_password": "securepassword123",
                    "smtp_encryption": "StartTLS",
                    "smtp_sender": "sender@example.com",
                },
            },
        )

    data = form_to_data(form)

    assert data["notifications-email_address"] == "primary@example.com"
    assert data["notifications-custom_smtp_settings"] is True
    assert data["notifications-smtp_settings-smtp_server"] == "smtp.example.com"
    assert data["notifications-smtp_settings-smtp_port"] == 587
    assert data["notifications-smtp_settings-smtp_username"] == "user@example.com"
    assert data["notifications-smtp_settings-smtp_password"] == "securepassword123"
    assert data["notifications-smtp_settings-smtp_encryption"] == "StartTLS"
    assert data["notifications-smtp_settings-smtp_sender"] == "sender@example.com"
    assert "notifications-update_email_forwarding" in data


def test_form_to_data_targets_only_selected_submit_button(app: Flask) -> None:
    with app.test_request_context():
        form = SetHomepageUsernameForm(data={"username": "target-user"})

    data = form_to_data(form, submit_name=form.delete_submit.name)

    assert data["username"] == "target-user"
    assert "delete_homepage_user" in data
    assert "set_homepage_user" not in data


def test_form_to_data_flattens_fieldlist_subforms(app: Flask) -> None:
    with app.test_request_context():
        form = _ChoiceListForm(
            formdata=MultiDict(
                {
                    "choices-0-choice": "First",
                    "choices-1-choice": "Second",
                    "save": "",
                }
            )
        )

    data = form_to_data(form, submit_name=form.submit.name)

    assert data["choices-0-choice"] == "First"
    assert data["choices-1-choice"] == "Second"
    assert "save" in data
