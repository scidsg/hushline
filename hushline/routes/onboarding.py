import requests
from flask import (
    Flask,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.crypto import can_encrypt_with_pgp_key, is_valid_pgp_key
from hushline.db import db
from hushline.model import User
from hushline.routes.forms import (
    OnboardingDirectoryForm,
    OnboardingNotificationsForm,
    OnboardingProfileForm,
    OnboardingSkipForm,
)
from hushline.settings.forms import PGPKeyForm, PGPProtonForm

HTTP_OK = 200
ONBOARDING_STEPS = {"profile", "encryption", "notifications", "directory"}
OnboardingStepForm = (
    OnboardingProfileForm
    | PGPProtonForm
    | PGPKeyForm
    | OnboardingNotificationsForm
    | OnboardingDirectoryForm
)


def _normalize_onboarding_step(step: str | None) -> str:
    if step in ONBOARDING_STEPS:
        return step
    return "profile"


def _submitted_onboarding_form(
    *,
    step: str,
    method: str | None,
    forms: dict[str, OnboardingStepForm],
) -> OnboardingStepForm | None:
    if step == "profile":
        return forms["profile"]
    if step == "encryption":
        if method == "proton":
            return forms["proton"]
        if method == "manual":
            return forms["manual"]
        return None
    if step == "notifications":
        return forms["notifications"]
    if step == "directory":
        return forms["directory"]
    return None


def register_onboarding_routes(app: Flask) -> None:
    @app.route("/onboarding", methods=["GET", "POST"])
    @authentication_required
    def onboarding() -> Response | str | tuple[str, int]:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        username = user.primary_username
        setup_incomplete = bool(
            not username
            or not (username.display_name or "").strip()
            or not (username.bio or "").strip()
            or not user.pgp_key
            or not user.enable_email_notifications
            or not user.email_include_message_content
            or not user.email_encrypt_entire_body
            or not user.enabled_notification_recipients
            or not username.show_in_directory
        )

        step = _normalize_onboarding_step(
            request.form.get("step", request.args.get("step", "profile"))
        )
        if user.onboarding_complete and not setup_incomplete and step == "profile":
            return redirect(url_for("inbox"))

        if not username:
            flash("⛔️ Unable to load your profile.")
            return redirect(url_for("inbox"))

        profile_form = OnboardingProfileForm()
        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm()
        notifications_form = OnboardingNotificationsForm()
        directory_form = OnboardingDirectoryForm()
        skip_form = OnboardingSkipForm()
        step_forms: dict[str, OnboardingStepForm] = {
            "profile": profile_form,
            "proton": pgp_proton_form,
            "manual": pgp_key_form,
            "notifications": notifications_form,
            "directory": directory_form,
        }
        submitted_form = None
        if request.method == "POST":
            submitted_form = _submitted_onboarding_form(
                step=step,
                method=request.form.get("method"),
                forms=step_forms,
            )

        if submitted_form is not profile_form:
            profile_form.display_name.data = username.display_name or ""
            profile_form.bio.data = username.bio or ""
        if submitted_form is not pgp_key_form:
            pgp_key_form.pgp_key.data = user.pgp_key
        if submitted_form is not notifications_form:
            notifications_form.email_address.data = (
                user.primary_notification_recipient.email
                if user.primary_notification_recipient
                else ""
            )
        if submitted_form is not directory_form:
            directory_form.show_in_directory.data = True

        status_code = 200
        if request.method == "POST":
            if step == "profile":
                if profile_form.validate():
                    username.display_name = profile_form.display_name.data.strip() or None
                    username.bio = profile_form.bio.data.strip()
                    db.session.commit()
                    return redirect(url_for("onboarding", step="encryption"))
                status_code = 400
            elif step == "encryption":
                if submitted_form is pgp_proton_form:
                    if pgp_proton_form.validate():
                        email = pgp_proton_form.email.data
                        try:
                            resp = requests.get(
                                f"https://mail-api.proton.me/pks/lookup?op=get&search={email}",
                                timeout=5,
                            )
                        except requests.exceptions.RequestException as exc:
                            current_app.logger.error(
                                "Error fetching PGP key from Proton Mail: %s", exc
                            )
                            flash("⛔️ Error fetching PGP key from Proton Mail.")
                            status_code = 400
                        else:
                            if resp.status_code == HTTP_OK and is_valid_pgp_key(resp.text):
                                if not can_encrypt_with_pgp_key(resp.text):
                                    flash(
                                        "⛔️ PGP key cannot be used for encryption. Please "
                                        "provide a key with an encryption subkey."
                                    )
                                    status_code = 400
                                else:
                                    # Prefill the manual key field so users can review/edit,
                                    # then continue with the normal save-and-advance action.
                                    pgp_key_form.pgp_key.data = resp.text
                            else:
                                flash("⛔️ No PGP key found for that email address.")
                                status_code = 400
                    else:
                        status_code = 400
                elif submitted_form is pgp_key_form:
                    if pgp_key_form.validate():
                        pgp_key = (pgp_key_form.pgp_key.data or "").strip()
                        if not pgp_key:
                            pgp_key_form.pgp_key.errors.append("PGP key is required.")
                            status_code = 400
                        elif is_valid_pgp_key(pgp_key):
                            if not can_encrypt_with_pgp_key(pgp_key):
                                pgp_key_form.pgp_key.errors.append(
                                    "PGP key cannot be used for encryption. Please provide a "
                                    "key with an encryption subkey."
                                )
                                status_code = 400
                            else:
                                user.pgp_key = pgp_key
                                db.session.commit()
                                return redirect(url_for("onboarding", step="notifications"))
                        else:
                            pgp_key_form.pgp_key.errors.append(
                                "Invalid PGP key format or import failed."
                            )
                            status_code = 400
                    else:
                        status_code = 400
                else:
                    status_code = 400
            elif step == "notifications":
                if not user.pgp_key:
                    flash("⛔️ Add a PGP key before enabling notifications.")
                    status_code = 400
                elif notifications_form.validate():
                    user.enable_email_notifications = True
                    user.email_include_message_content = True
                    user.email_encrypt_entire_body = True
                    user.email = notifications_form.email_address.data.strip()
                    db.session.commit()
                    return redirect(url_for("onboarding", step="directory"))
                else:
                    status_code = 400
            elif step == "directory":
                if directory_form.validate():
                    username.show_in_directory = directory_form.show_in_directory.data
                    user.onboarding_complete = True
                    db.session.commit()
                    flash("🎉 Congratulations! Your account setup is complete!")

                    if current_app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
                        return redirect(url_for("premium.select_tier"))
                    return redirect(url_for("inbox"))
                else:
                    status_code = 400

        return render_template(
            "onboarding.html",
            step=step,
            profile_form=profile_form,
            pgp_proton_form=pgp_proton_form,
            pgp_key_form=pgp_key_form,
            notifications_form=notifications_form,
            directory_form=directory_form,
            skip_form=skip_form,
        ), status_code

    @app.route("/onboarding/skip", methods=["POST"])
    @authentication_required
    def onboarding_skip() -> Response:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        form = OnboardingSkipForm()
        if not form.validate_on_submit():
            return redirect(url_for("onboarding"))

        user.onboarding_complete = True
        db.session.commit()

        if current_app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
            return redirect(url_for("premium.select_tier"))
        return redirect(url_for("inbox"))
