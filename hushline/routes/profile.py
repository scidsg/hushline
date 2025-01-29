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
from werkzeug.wrappers.response import Response

from hushline.db import db
from hushline.model import (
    FieldDefinition,
    FieldValue,
    Message,
    OrganizationSetting,
    Username,
)
from hushline.routes.common import do_send_email, validate_captcha
from hushline.routes.forms import DynamicMessageForm
from hushline.safe_template import safe_render_template


def register_profile_routes(app: Flask) -> None:
    @app.route("/to/<username>")
    def profile(username: str) -> Response | str:
        uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one_or_none()
        if not uname:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        uname.create_default_field_defs()

        dynamic_form = DynamicMessageForm(uname.message_fields)
        form = dynamic_form.form()

        # Generate a simple math problem using secrets module (e.g., "What is 6 + 7?")
        num1 = secrets.randbelow(10) + 1
        num2 = secrets.randbelow(10) + 1
        math_problem = f"{num1} + {num2} ="
        session["math_answer"] = str(num1 + num2)  # Store the answer in session as a string

        profile_header = safe_render_template(
            OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE),
            {
                "display_name_or_username": uname.display_name or uname.username,
                "display_name": uname.display_name,
                "username": uname.username,
            },
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

    @app.route("/to/<username>", methods=["POST"])
    def submit_message(username: str) -> Response | str:
        uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one_or_none()
        if not uname:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        dynamic_form = DynamicMessageForm(uname.message_fields)
        form = dynamic_form.form()

        current_app.logger.debug(f"Form submitted: {form.data}")

        if form.validate_on_submit():
            if not uname.user.pgp_key:
                flash("⛔️ You cannot submit messages to users who have not set a PGP key.", "error")
                return redirect(url_for("profile", username=username))

            captcha_answer = request.form.get("captcha_answer", "")
            if not validate_captcha(captcha_answer):
                flash("⛔️ Invalid CAPTCHA answer.", "error")
                return redirect(url_for("profile", username=username))

            current_app.logger.debug(f"Form submitted: {form.data}")

            client_side_encrypted = request.form.get("client_side_encrypted", "false") == "true"

            email_body = ""

            # Create a message
            message = Message(username_id=uname.id)
            db.session.add(message)
            db.session.commit()

            # Add the field values
            for data in dynamic_form.field_data():
                field_name: str = data["name"]  # type: ignore
                field_definition: FieldDefinition = data["field"]  # type: ignore
                value = getattr(form, field_name).data
                field_value = FieldValue(
                    field_definition,
                    message,
                    value,
                    field_definition.encrypted,
                    client_side_encrypted,
                )
                db.session.add(field_value)
                db.session.commit()

                email_body += f"{field_definition.label}\n\n{field_value.value}\n\n\n"

            do_send_email(uname.user, email_body)
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
        return redirect(url_for("profile", username=username))

    @app.route("/submit/success")
    def submission_success() -> Response | str:
        reply_slug = session.pop("reply_slug", None)
        if not reply_slug:
            current_app.logger.debug(
                "Attempted to access submission_success endpoint without a reply_slug in session"
            )
            return redirect(url_for("directory"))

        msg = db.session.scalars(
            db.session.query(Message).filter_by(reply_slug=reply_slug)
        ).one_or_none()
        if msg is None:
            abort(404)

        return render_template("submission_success.html", message=msg)
