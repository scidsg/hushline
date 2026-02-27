from typing import Tuple

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from werkzeug.wrappers.response import Response
from wtforms import BooleanField, IntegerField, SubmitField
from wtforms.validators import DataRequired
from wtforms.validators import Optional as OptionalField

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.forms import Button, DisplayNoneButton
from hushline.model import InviteCode, OrganizationSetting


class ToggleRegistrationForm(FlaskForm):
    registration_enabled = BooleanField("Enable Registrations", validators=[OptionalField()])
    submit = SubmitField("Submit", name="registration_enabled", widget=DisplayNoneButton())


class ToggleRegistrationCodesForm(FlaskForm):
    registration_codes_required = BooleanField(
        "Require Registration Codes", validators=[OptionalField()]
    )
    submit = SubmitField("Submit", name="registration_codes_required", widget=DisplayNoneButton())


class CreateInviteCodeForm(FlaskForm):
    submit = SubmitField("Create Invite Code", name="create_invite_code", widget=Button())


class DeleteInviteCodeForm(FlaskForm):
    invite_code_id = IntegerField(validators=[DataRequired()])
    submit = SubmitField("Delete", name="delete_invite_code", widget=Button())


def register_registration_routes(bp: Blueprint) -> None:
    @bp.route("/registration", methods=["GET", "POST"])
    @admin_authentication_required
    def registration() -> Tuple[str, int] | Response:
        if not current_app.config["REGISTRATION_SETTINGS_ENABLED"]:
            return abort(401)

        toggle_registration_form = ToggleRegistrationForm()
        toggle_registration_codes_form = ToggleRegistrationCodesForm()

        create_invite_code_form = CreateInviteCodeForm()
        delete_invite_code_form = DeleteInviteCodeForm()

        status_code = 200
        if request.method == "POST":
            # Registration enabled
            if (
                toggle_registration_form.submit.name in request.form
                and toggle_registration_form.validate()
            ):
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
            # Registration codes required
            elif (
                toggle_registration_codes_form.submit.name in request.form
                and toggle_registration_codes_form.validate()
            ):
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
            # Create invite code
            elif (
                create_invite_code_form.submit.name in request.form
                and create_invite_code_form.validate()
            ):
                new_invite_code = InviteCode()
                db.session.add(new_invite_code)
                db.session.commit()
                flash(f"👍 Invite code {new_invite_code.code} created.")
                return redirect(url_for(".registration"))
            # Delete invite code
            elif (
                delete_invite_code_form.submit.name in request.form
                and delete_invite_code_form.validate()
            ):
                invite_code = db.session.scalars(
                    db.select(InviteCode).filter_by(id=delete_invite_code_form.invite_code_id.data)
                ).one_or_none()
                if invite_code is None:
                    flash("⛔️ Invite code not found.")
                    return redirect(url_for(".registration"))
                db.session.delete(invite_code)
                db.session.commit()
                flash(f"👍 Invite code {invite_code.code} deleted.")
                return redirect(url_for(".registration"))
            else:
                flash("⛔️ Invalid form submission.")
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

        invite_codes = db.session.scalars(
            db.select(InviteCode).order_by(InviteCode.expiration_date.desc())
        ).all()

        return render_template(
            "settings/registration.html",
            toggle_registration_form=toggle_registration_form,
            toggle_registration_codes_form=toggle_registration_codes_form,
            create_invite_code_form=create_invite_code_form,
            delete_invite_code_form=delete_invite_code_form,
            invite_codes=invite_codes,
        ), status_code
