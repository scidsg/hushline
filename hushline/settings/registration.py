from typing import Tuple

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from werkzeug.wrappers.response import Response
from wtforms import BooleanField, SubmitField
from wtforms.validators import Optional as OptionalField

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.forms import DisplayNoneButton
from hushline.model import OrganizationSetting


class ToggleRegistrationForm(FlaskForm):
    registration_enabled = BooleanField("Enable Registrations", validators=[OptionalField()])
    submit = SubmitField("Submit", name="registration_enabled", widget=DisplayNoneButton())


class ToggleRegistrationCodesForm(FlaskForm):
    registration_codes_required = BooleanField(
        "Require Registration Codes", validators=[OptionalField()]
    )
    submit = SubmitField("Submit", name="registration_codes_required", widget=DisplayNoneButton())


def register_registration_routes(bp: Blueprint) -> None:
    @bp.route("/registration", methods=["GET", "POST"])
    @admin_authentication_required
    def registration() -> Tuple[str, int] | Response:
        toggle_registration_form = ToggleRegistrationForm()
        toggle_registration_codes_form = ToggleRegistrationCodesForm()

        status_code = 200
        if request.method == "POST":
            if (
                toggle_registration_form.submit.name in request.form
                and toggle_registration_form.validate()
            ):
                current_app.logger.info(
                    f"Registration enabled: {toggle_registration_form}"
                )
                OrganizationSetting.upsert(
                    key=OrganizationSetting.REGISTRATION_ENABLED,
                    value=toggle_registration_form.registration_enabled.data,
                )
                db.session.commit()
                if toggle_registration_form.registration_enabled.data:
                    flash("👍 Registration enabled.")
                else:
                    flash("👍 Registration disabled.")
                return redirect(url_for(".registration"))
            elif (
                toggle_registration_codes_form.submit.name in request.form
                and toggle_registration_codes_form.validate()
            ):
                current_app.logger.info(
                    f"Registration codes required: {toggle_registration_codes_form}"
                )
                OrganizationSetting.upsert(
                    key=OrganizationSetting.REGISTRATION_CODES_REQUIRED,
                    value=toggle_registration_codes_form.registration_codes_required.data,
                )
                db.session.commit()
                if toggle_registration_codes_form.registration_codes_required.data:
                    flash("👍 Registration codes required.")
                else:
                    flash("👍 Registration codes not required.")
                return redirect(url_for(".registration"))

        registration_enabled = OrganizationSetting.fetch_one(
            OrganizationSetting.REGISTRATION_ENABLED
        )
        registration_codes_required = OrganizationSetting.fetch_one(
            OrganizationSetting.REGISTRATION_CODES_REQUIRED
        )

        toggle_registration_form.registration_enabled.data = registration_enabled
        toggle_registration_codes_form.registration_codes_required.data = (
            registration_codes_required
        )

        return render_template(
            "settings/registration.html",
            toggle_registration_form=toggle_registration_form,
            toggle_registration_codes_form=toggle_registration_codes_form,
        ), status_code
