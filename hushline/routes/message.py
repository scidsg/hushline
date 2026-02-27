from datetime import UTC, datetime

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.crypto import encrypt_message
from hushline.db import db
from hushline.forms import DeleteMessageForm, ResendMessageForm, UpdateMessageStatusForm
from hushline.model import (
    FieldValue,
    Message,
    User,
    Username,
)
from hushline.routes.common import do_send_email


def register_message_routes(app: Flask) -> None:
    @app.route("/message/<public_id>")
    @authentication_required
    def message(public_id: str) -> str:
        msg = db.session.scalars(
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == session["user_id"], Message.public_id == public_id)
        ).one_or_none()

        if not msg:
            abort(404)

        update_status_form = UpdateMessageStatusForm(data={"status": msg.status.value})
        delete_message_form = DeleteMessageForm()
        resend_message_form = ResendMessageForm()

        return render_template(
            "message.html",
            message=msg,
            update_status_form=update_status_form,
            delete_message_form=delete_message_form,
            resend_message_form=resend_message_form,
        )

    @app.route("/reply/<slug>")
    def message_reply(slug: str) -> str:
        msg = db.session.scalars(db.select(Message).filter_by(reply_slug=slug)).one_or_none()
        if msg is None:
            abort(404)

        return render_template("reply.html", message=msg)

    @app.route("/message/<public_id>/delete", methods=["POST"])
    @authentication_required
    def delete_message(public_id: str) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        message = db.session.scalars(
            db.select(Message).where(
                Message.public_id == public_id,
                Message.username_id.in_(
                    db.select(Username.id).select_from(Username).filter(Username.user_id == user.id)
                ),
            )
        ).one_or_none()
        if message:
            db.session.execute(db.delete(FieldValue).where(FieldValue.message_id == message.id))
            db.session.commit()

            db.session.delete(message)
            db.session.commit()
            flash("🗑️ Message deleted successfully.")
        else:
            flash("⛔️ Message not found.")

        return redirect(url_for("inbox"))

    @app.route("/message/<public_id>/resend", methods=["POST"])
    @authentication_required
    def resend_message(public_id: str) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        form = ResendMessageForm()
        if not form.validate_on_submit():
            flash("⛔️ Invalid resend request.")
            return redirect(url_for("message", public_id=public_id))

        message = db.session.scalars(
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == user.id, Message.public_id == public_id)
        ).one_or_none()
        if not message:
            flash("⛔️ Message not found.")
            return redirect(url_for("inbox"))

        if not user.enable_email_notifications:
            flash("⛔️ Email notifications are disabled.")
            return redirect(url_for("message", public_id=public_id))

        extracted_fields = [
            (field_value.field_definition.label, field_value.value or "")
            for field_value in message.field_values
        ]
        generic_body = "You have a new Hush Line message! Please log in to read it."

        if user.email_include_message_content:
            sent_any = False
            for _, value in extracted_fields:
                if not value:
                    continue
                if user.email_encrypt_entire_body:
                    if "-----BEGIN PGP MESSAGE-----" in value:
                        email_body = value
                    else:
                        try:
                            email_body = (
                                encrypt_message(value, user.pgp_key) if user.pgp_key else None
                            )
                        except (RuntimeError, TypeError, ValueError) as e:
                            current_app.logger.error(
                                "Failed to encrypt email body: %s", str(e), exc_info=True
                            )
                            email_body = None
                    do_send_email(user, (email_body or generic_body).strip())
                else:
                    do_send_email(user, value.strip())
                sent_any = True
            if not sent_any:
                do_send_email(user, generic_body)
        else:
            do_send_email(user, generic_body)
        flash("📧 Message resent to your email inbox.")
        return redirect(url_for("message", public_id=public_id))

    @app.route("/message/<public_id>/status", methods=["POST"])
    @authentication_required
    def set_message_status(public_id: str) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        form = UpdateMessageStatusForm()
        if not form.validate():
            flash(f"⛔️ Invalid status: {form.status.data}.")
            return redirect(url_for("message", public_id=public_id))

        row_count = db.session.execute(
            db.update(Message)
            .where(
                Message.public_id == public_id,
                Message.username_id.in_(
                    db.select(Username.id).select_from(Username).filter(Username.user_id == user.id)
                ),
            )
            .values(status=form.status.data, status_changed_at=datetime.now(UTC))
        ).rowcount
        match row_count:
            case 1:
                db.session.commit()
                flash("👍 Message status updated.")
            case 0:
                db.session.rollback()
                flash("⛔️ Message not found.")
            case _:
                db.session.rollback()
                current_app.logger.error(
                    "Multiple messages would have been updated. "
                    f"Message.public_id={public_id} User.id={user.id}"
                )
                flash("⛔️ Internal server error. Message not updated.")
        return redirect(url_for("message", public_id=public_id))
