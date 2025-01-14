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

from hushline.crypto import encrypt_field, encrypt_message, generate_salt
from hushline.db import db
from hushline.model import (
    Message,
    Username,
)
from hushline.routes.common import do_send_email, validate_captcha
from hushline.routes.forms import MessageForm


def register_submit_routes(app: Flask) -> None:
    @app.route("/submit_message/<username>")
    def redirect_submit_message(username: str) -> Response:
        return redirect(url_for("profile", username=username), 301)

    @app.route("/to/<username>", methods=["POST"])
    def submit_message(username: str) -> Response | str:
        form = MessageForm()
        uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one_or_none()
        if not uname:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        if form.validate_on_submit():
            if not uname.user.pgp_key and app.config["REQUIRE_PGP"]:
                flash("⛔️ You cannot submit messages to users who have not set a PGP key.", "error")
                return redirect(url_for("profile", username=username))

            captcha_answer = request.form.get("captcha_answer", "")
            if not validate_captcha(captcha_answer):
                # Encrypt the message and store it in the session
                scope = "submit_message"
                salt = generate_salt()
                session[f"{scope}:contact_method"] = encrypt_field(
                    form.contact_method.data, scope, salt
                )
                session[f"{scope}:content"] = encrypt_field(form.content.data, scope, salt)
                session[f"{scope}:salt"] = salt

                return redirect(url_for("profile", username=username))

            content = form.content.data
            contact_method = form.contact_method.data.strip() if form.contact_method.data else ""
            full_content = (
                f"Contact Method: {contact_method}\n\n{content}" if contact_method else content
            )
            client_side_encrypted = request.form.get("client_side_encrypted", "false") == "true"

            if client_side_encrypted:
                content_to_save = (
                    content  # Assume content is already encrypted and includes contact method
                )
            elif uname.user.pgp_key:
                try:
                    encrypted_content = encrypt_message(full_content, uname.user.pgp_key)
                    if not encrypted_content:
                        flash("⛔️ Failed to encrypt message.", "error")
                        return redirect(url_for("profile", username=username))
                    content_to_save = encrypted_content
                except Exception as e:
                    app.logger.error("Encryption failed: %s", str(e), exc_info=True)
                    flash("⛔️ Failed to encrypt message.", "error")
                    return redirect(url_for("profile", username=username))
            else:
                content_to_save = full_content

            new_message = Message(content=content_to_save, username_id=uname.id)
            db.session.add(new_message)
            db.session.commit()

            do_send_email(uname.user, content_to_save)
            flash("👍 Message submitted successfully.")
            session["reply_slug"] = new_message.reply_slug
            return redirect(url_for("submission_success"))

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
