import re
from datetime import UTC, datetime
from typing import Any

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import validate_csrf
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import authentication_required
from hushline.crypto import encrypt_message
from hushline.db import db
from hushline.forms import (
    ConversationMessageForm,
    DeleteMessageForm,
    ResendMessageForm,
    UpdateMessageStatusForm,
)
from hushline.model import (
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    FieldValue,
    Message,
    User,
    Username,
)
from hushline.routes.common import do_send_email, notification_email_encryption_target

_CHAT_CIPHERTEXT_MAX_LENGTH = 200_000
_ARMORED_PGP_MESSAGE_PATTERN = re.compile(
    r"^\s*-----BEGIN PGP MESSAGE-----\r?\n"
    r"(?:[!-~]+: .*\r?\n)*\r?\n?[\s\S]*\r?\n"
    r"-----END PGP MESSAGE-----\s*$"
)


def _conversation_latest_message(thread: Conversation) -> ConversationMessage | None:
    if not thread.messages:
        return None

    return max(
        thread.messages,
        key=lambda message: (message.created_at, message.id),
    )


def _is_armored_pgp_message(value: str) -> bool:
    return bool(_ARMORED_PGP_MESSAGE_PATTERN.fullmatch(value))


def _validate_json_csrf() -> str | None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return None

    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    try:
        validate_csrf(token)
    except ValidationError:
        return "Invalid CSRF token."
    return None


def _is_chat_ciphertext_envelope(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > _CHAT_CIPHERTEXT_MAX_LENGTH:
        return False

    try:
        envelope = current_app.json.loads(value)
    except ValueError:
        return False

    if not isinstance(envelope, dict):
        return False

    return (
        all(
            isinstance(envelope.get(field), str) and envelope[field]
            for field in ("algorithm", "ephemeral_public_key", "iv", "ciphertext")
        )
        and envelope["algorithm"] == "ECDH-P256-AES-GCM"
    )


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

    @app.route("/conversation/<int:conversation_id>")
    @authentication_required
    def conversation(conversation_id: int) -> str:
        user = db.session.get(User, session["user_id"])
        if not user:
            abort(404)

        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.id == conversation_id)
        ).one_or_none()
        if not thread:
            abort(404)

        participant = thread.participant_for_user_id(user.id)
        if not participant:
            abort(404)

        latest_message = _conversation_latest_message(thread)
        if latest_message and (
            participant.last_read_at is None or latest_message.created_at > participant.last_read_at
        ):
            participant.last_read_at = latest_message.created_at
            db.session.commit()

        message_copies = []
        message_copy_payloads = []
        for conversation_message in thread.messages:
            copy = next(
                (
                    encrypted_copy
                    for encrypted_copy in conversation_message.encrypted_copies
                    if encrypted_copy.recipient_participant_id == participant.id
                ),
                None,
            )
            message_copies.append((conversation_message, copy))
            message_copy_payloads.append(
                {
                    "message_id": conversation_message.id,
                    "created_at": conversation_message.created_at.isoformat(),
                    "sender_participant_id": conversation_message.sender_participant_id,
                    "encrypted_payload": copy.encrypted_payload if copy else None,
                }
            )

        participant_public_keys = [
            {
                "participant_id": thread_participant.id,
                "public_key": thread_participant.user.chat_public_key,
            }
            for thread_participant in thread.participants
            if thread_participant.user and thread_participant.user.chat_public_key
        ]
        can_compose = len(participant_public_keys) == len(thread.participants)
        conversation_message_form = ConversationMessageForm()

        return render_template(
            "conversation.html",
            conversation=thread,
            participant=participant,
            message_copies=message_copies,
            message_copy_payloads=message_copy_payloads,
            participant_public_keys=participant_public_keys,
            can_compose=can_compose,
            conversation_message_form=conversation_message_form,
        )

    @app.route("/conversation/<int:conversation_id>/messages", methods=["POST"])
    @authentication_required
    def append_conversation_message(conversation_id: int) -> tuple[Response, int]:
        user = db.session.get(User, session["user_id"])
        if not user:
            abort(404)

        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.id == conversation_id)
        ).one_or_none()
        if not thread:
            abort(404)

        participant = thread.participant_for_user_id(user.id)
        if not participant:
            abort(404)

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return jsonify({"error": csrf_error}), 400

        payload: Any = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        encrypted_copies = payload.get("encrypted_copies")
        if not isinstance(encrypted_copies, dict):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        participant_public_keys = {
            str(thread_participant.id): thread_participant.user.chat_public_key
            for thread_participant in thread.participants
            if thread_participant.user and thread_participant.user.chat_public_key
        }
        if len(participant_public_keys) != len(thread.participants):
            return jsonify({"error": "Conversation replies are unavailable."}), 400

        if set(encrypted_copies.keys()) != set(participant_public_keys.keys()):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        if not all(_is_chat_ciphertext_envelope(value) for value in encrypted_copies.values()):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        conversation_message = ConversationMessage()
        conversation_message.conversation = thread
        conversation_message.sender_participant = participant
        for recipient_participant in thread.participants:
            encrypted_copy = ConversationMessageCopy()
            encrypted_copy.recipient_participant = recipient_participant
            encrypted_copy.encrypted_payload = encrypted_copies[str(recipient_participant.id)]
            conversation_message.encrypted_copies.append(encrypted_copy)
        db.session.add(conversation_message)
        db.session.commit()

        return (
            jsonify(
                {
                    "message_id": conversation_message.id,
                    "created_at": conversation_message.created_at.isoformat(),
                }
            ),
            201,
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
        notification_encryption_target = notification_email_encryption_target(user)

        if user.email_include_message_content:
            sent_any = False
            for _, value in extracted_fields:
                if not value:
                    continue
                if user.email_encrypt_entire_body:
                    value_is_armored = _is_armored_pgp_message(value)
                    if value_is_armored and isinstance(notification_encryption_target, str):
                        email_body = value
                    else:
                        try:
                            email_body = (
                                encrypt_message(value, notification_encryption_target)
                                if notification_encryption_target and not value_is_armored
                                else None
                            )
                            if value_is_armored and not isinstance(
                                notification_encryption_target, str
                            ):
                                current_app.logger.warning(
                                    "Cannot reuse single-recipient armored resend body for "
                                    "multi-recipient delivery; sending generic notification."
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
