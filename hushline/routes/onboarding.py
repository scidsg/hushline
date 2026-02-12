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
            or not user.email
            or not username.show_in_directory
        )

        step = request.form.get("step", request.args.get("step", "profile"))
        if user.onboarding_complete and not setup_incomplete and step == "profile":
            return redirect(url_for("inbox"))

        if not username:
            flash("⛔️ Unable to load your profile.")
            return redirect(url_for("inbox"))

        if step not in {"profile", "encryption", "notifications", "directory"}:
            step = "profile"
        profile_form = OnboardingProfileForm(
            data={
                "display_name": username.display_name or "",
                "bio": username.bio or "",
            }
        )
        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm(pgp_key=user.pgp_key)
        notifications_form = OnboardingNotificationsForm(data={"email_address": user.email or ""})
        directory_form = OnboardingDirectoryForm(data={"show_in_directory": True})
        skip_form = OnboardingSkipForm()

        status_code = 200
        if request.method == "POST":
            step = request.form.get("step", step)
            if step not in {"profile", "encryption", "notifications", "directory"}:
                step = "profile"
            if step == "profile":
                if profile_form.validate_on_submit():
                    username.display_name = profile_form.display_name.data.strip() or None
                    username.bio = profile_form.bio.data.strip()
                    db.session.commit()
                    return redirect(url_for("onboarding", step="encryption"))
                status_code = 400
            elif step == "encryption":
                method = request.form.get("method")
                if method == "proton":
                    if not pgp_proton_form.validate_on_submit():
                        status_code = 400
                    else:
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
                elif method == "manual":
                    if not pgp_key_form.validate_on_submit():
                        status_code = 400
                    else:
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
            elif step == "notifications":
                if not user.pgp_key:
                    flash("⛔️ Add a PGP key before enabling notifications.")
                    status_code = 400
                elif notifications_form.validate_on_submit():
                    user.enable_email_notifications = True
                    user.email_include_message_content = True
                    user.email_encrypt_entire_body = True
                    user.email = notifications_form.email_address.data.strip()
                    db.session.commit()
                    return redirect(url_for("onboarding", step="directory"))
                else:
                    status_code = 400
            elif step == "directory":
                if directory_form.validate_on_submit():
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
