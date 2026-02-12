import secrets

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func
from werkzeug.wrappers.response import Response

from hushline.crypto import encrypt_message
from hushline.db import db
from hushline.model import (
    FieldDefinition,
    FieldValue,
    Message,
    OrganizationSetting,
    Username,
)
from hushline.routes.common import (
    do_send_email,
    format_full_message_email_body,
    format_message_email_fields,
    validate_captcha,
)
from hushline.routes.forms import DynamicMessageForm
from hushline.safe_template import safe_render_template


def register_profile_routes(app: Flask) -> None:
    def _is_armored_pgp_message(value: str) -> bool:
        return "-----BEGIN PGP MESSAGE-----" in value and "-----END PGP MESSAGE-----" in value

    def _get_math_problem(force_new: bool = False) -> str:
        if not force_new and session.get("math_problem") and session.get("math_answer"):
            return session["math_problem"]
        num1 = secrets.randbelow(10) + 1
        num2 = secrets.randbelow(10) + 1
        math_problem = f"{num1} + {num2} ="
        session["math_answer"] = str(num1 + num2)
        session["math_problem"] = math_problem
        return math_problem

    @app.route("/to/<username>", methods=["GET", "POST"])
    def profile(username: str) -> Response | str | tuple[str, int]:
        uname = db.session.scalars(
            db.select(Username).where(func.lower(Username._username) == username.lower())
        ).one_or_none()
        if not uname:
            abort(404)

        uname.create_default_field_defs()

        dynamic_form = DynamicMessageForm([x for x in uname.message_fields if x.enabled])
        form = dynamic_form.form()

        math_problem = _get_math_problem(force_new=request.method == "GET")

        profile_header = safe_render_template(
            OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE),
            {
                "display_name_or_username": uname.display_name or uname.username,
                "display_name": uname.display_name,
                "username": uname.username,
            },
        )

        if request.method == "POST":
            current_app.logger.debug(f"Form submitted: {form.data}")
            submitted_user_id = request.form.get("username_user_id")
            if not submitted_user_id or submitted_user_id != str(uname.user_id):
                flash("⛔️ This tip line changed while you were composing. Please reload.")
                return (
                    render_template(
                        "profile.html",
                        profile_header=profile_header,
                        form=form,
                        user=uname.user,
                        username=uname,
                        field_data=dynamic_form.field_data(),
                        display_name_or_username=uname.display_name or uname.username,
                        current_user_id=session.get("user_id"),
                        public_key=uname.user.pgp_key,
                        math_problem=math_problem,
                    ),
                    400,
                )

            if form.validate_on_submit():
                if not uname.user.pgp_key:
                    flash(
                        "⛔️ You cannot submit messages to users who have not set a PGP key.",
                        "error",
                    )
                    return (
                        render_template(
                            "profile.html",
                            profile_header=profile_header,
                            form=form,
                            user=uname.user,
                            username=uname,
                            field_data=dynamic_form.field_data(),
                            display_name_or_username=uname.display_name or uname.username,
                            current_user_id=session.get("user_id"),
                            public_key=uname.user.pgp_key,
                            math_problem=math_problem,
                        ),
                        400,
                    )

                captcha_answer = request.form.get("captcha_answer", "")
                if not validate_captcha(captcha_answer):
                    flash("⛔️ Invalid CAPTCHA answer.", "error")
                    return (
                        render_template(
                            "profile.html",
                            profile_header=profile_header,
                            form=form,
                            user=uname.user,
                            username=uname,
                            field_data=dynamic_form.field_data(),
                            display_name_or_username=uname.display_name or uname.username,
                            current_user_id=session.get("user_id"),
                            public_key=uname.user.pgp_key,
                            math_problem=math_problem,
                        ),
                        400,
                    )

                # Create a message
                message = Message(username_id=uname.id)
                db.session.add(message)
                db.session.flush()

                extracted_fields = []
                raw_extracted_fields = []
                # Add the field values
                for data in dynamic_form.field_data():
                    field_name: str = data["name"]  # type: ignore
                    field_definition: FieldDefinition = data["field"]  # type: ignore
                    value = getattr(form, field_name).data
                    raw_value = "\n".join(value) if isinstance(value, list) else (value or "")
                    raw_extracted_fields.append((field_definition.label, str(raw_value)))
                    field_value = FieldValue(
                        field_definition,
                        message,
                        value,
                        field_definition.encrypted,
                    )
                    db.session.add(field_value)
                    db.session.flush()
                    extracted_fields.append((field_definition.label, field_value.value or ""))

                db.session.commit()

                plaintext_new_message_body = (
                    "You have a new Hush Line message! Please log in to read it."
                )
                if uname.user.enable_email_notifications:
                    if uname.user.email_include_message_content:
                        if uname.user.email_encrypt_entire_body:
                            encrypted_email_body = (form.encrypted_email_body.data or "").strip()
                            if _is_armored_pgp_message(encrypted_email_body):
                                email_body = encrypted_email_body
                                current_app.logger.debug("Sending email with encrypted body")
                            else:
                                fallback_body = format_full_message_email_body(raw_extracted_fields)
                                try:
                                    if fallback_body and uname.user.pgp_key:
                                        email_body = encrypt_message(
                                            fallback_body, uname.user.pgp_key
                                        )
                                        current_app.logger.warning(
                                            "Missing/invalid client encrypted email body; "
                                            "used server-side full-body encryption fallback."
                                        )
                                    else:
                                        email_body = plaintext_new_message_body
                                        current_app.logger.debug(
                                            "No fallback email content available; "
                                            "sending generic body."
                                        )
                                except (RuntimeError, TypeError, ValueError) as e:
                                    current_app.logger.error(
                                        "Failed to encrypt fallback full email body: %s",
                                        str(e),
                                        exc_info=True,
                                    )
                                    email_body = plaintext_new_message_body
                        else:
                            # Keep the existing field-level email behavior
                            # when full-body encryption is disabled.
                            email_body = format_message_email_fields(extracted_fields)
                            current_app.logger.debug("Sending email with unencrypted body")
                    else:
                        email_body = plaintext_new_message_body
                        current_app.logger.debug("Sending email with generic body")

                    do_send_email(uname.user, email_body.strip())

                flash("👍 Message submitted successfully.")
                session["reply_slug"] = message.reply_slug
                current_app.logger.debug("Message sent and now redirecting")
                return redirect(url_for("submission_success"))

            errors = []
            for field, field_errors in form.errors.items():
                for error in field_errors:
                    field_def = dynamic_form.field_from_name(field)
                    label = field_def.label if field_def else "unknown"
                    errors.append(f"{label}: {error}")
                    current_app.logger.debug(f"Error in field {field}: {error}")

            error_message = "⛔️ There was an error submitting your message: " + "; ".join(errors)
            flash(error_message, "error")
            return (
                render_template(
                    "profile.html",
                    profile_header=profile_header,
                    form=form,
                    user=uname.user,
                    username=uname,
                    field_data=dynamic_form.field_data(),
                    display_name_or_username=uname.display_name or uname.username,
                    current_user_id=session.get("user_id"),
                    public_key=uname.user.pgp_key,
                    math_problem=math_problem,
                ),
                400,
            )

        return render_template(
            "profile.html",
            profile_header=profile_header,
            form=form,
            user=uname.user,
            username=uname,
            field_data=dynamic_form.field_data(),
            display_name_or_username=uname.display_name or uname.username,
            current_user_id=session.get("user_id"),
            public_key=uname.user.pgp_key,
            math_problem=math_problem,
        )

    @app.route("/submit_message/<username>")
    def redirect_submit_message(username: str) -> Response:
        return redirect(url_for("profile", username=username), 301)

    @app.route("/submit/success")
    def submission_success() -> Response | str:
        reply_slug = session.pop("reply_slug", None)
        if not reply_slug:
            current_app.logger.debug(
                "Attempted to access submission_success endpoint without a reply_slug in session"
            )
            return redirect(url_for("directory"))

        msg = db.session.scalars(db.select(Message).filter_by(reply_slug=reply_slug)).one_or_none()
        if msg is None:
            abort(404)

        return render_template("submission_success.html", message=msg)
