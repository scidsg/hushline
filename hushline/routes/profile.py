import hmac
import json
import re
import secrets
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import MultipleResultsFound
from werkzeug.wrappers.response import Response

from hushline.auth import get_session_user
from hushline.crypto import encrypt_message
from hushline.db import db
from hushline.embeds import (
    EMBED_SUBMISSION_ACCEPTED_COUNTER,
    EMBED_SUBMISSION_ATTEMPT_COUNTER,
    EMBED_SUBMISSION_RATE_LIMITED_COUNTER,
    EMBED_SUBMISSION_REJECTED_COUNTER,
    check_embed_rate_limit,
    emit_embed_abuse_counter,
)
from hushline.external_urls import canonical_external_url
from hushline.model import (
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    FieldDefinition,
    FieldValue,
    Message,
    NotificationRecipient,
    OrganizationSetting,
    User,
    Username,
)
from hushline.routes.common import (
    do_send_email,
    format_full_message_email_body,
    format_message_email_fields,
    notification_email_encryption_target,
    notification_recipient_public_key_entries,
    send_email_to_user_recipients,
    show_directory_caution_badge,
    validate_captcha,
)
from hushline.routes.forms import DynamicMessageForm
from hushline.safe_template import safe_render_template

EMBED_CAPTCHA_MAX_AGE_SECONDS = 60 * 60


def register_profile_routes(app: Flask) -> None:
    def _owner_guard_signature(username: str, user_id: int, nonce: str) -> str:
        return hmac.new(
            key=(app.secret_key or "").encode("utf-8"),
            msg=f"{username}:{user_id}:{nonce}".encode(),
            digestmod=sha256,
        ).hexdigest()

    def _embed_captcha_serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(app.secret_key or "", salt="embed-profile-captcha")

    def _embed_captcha_answer_signature(
        username: str,
        user_id: int,
        nonce: str,
        math_problem: str,
        captcha_answer: str,
    ) -> str:
        return hmac.new(
            key=(app.secret_key or "").encode("utf-8"),
            msg=(
                "embed-captcha:v1:" f"{username}:{user_id}:{nonce}:{math_problem}:{captcha_answer}"
            ).encode(),
            digestmod=sha256,
        ).hexdigest()

    def _is_armored_pgp_message(value: str) -> bool:
        stripped_value = value.strip()
        return bool(
            re.fullmatch(
                r"-----BEGIN PGP MESSAGE-----\r?\n"
                r"(?:[!-~]+: .*\r?\n)*\r?\n?[\s\S]*\r?\n"
                r"-----END PGP MESSAGE-----",
                stripped_value,
            )
        )

    def _client_encrypted_email_fields_by_recipient(
        value: str,
    ) -> dict[int, dict[str, str]]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        encrypted_fields: dict[int, dict[str, str]] = {}
        for recipient_id, fields in parsed.items():
            if not isinstance(recipient_id, str) or not recipient_id.isdigit():
                continue
            if not isinstance(fields, dict):
                continue
            encrypted_fields[int(recipient_id)] = {
                field_name: field_value
                for field_name, field_value in fields.items()
                if isinstance(field_name, str)
                and isinstance(field_value, str)
                and _is_armored_pgp_message(field_value)
            }
        return encrypted_fields

    def _new_math_problem() -> tuple[str, str]:
        num1 = secrets.randbelow(10) + 1
        num2 = secrets.randbelow(10) + 1
        math_problem = f"{num1} + {num2} ="
        return math_problem, str(num1 + num2)

    def _get_session_math_problem(force_new: bool = False) -> str:
        if not force_new and session.get("math_problem") and session.get("math_answer"):
            return session["math_problem"]
        math_problem, math_answer = _new_math_problem()
        session["math_answer"] = math_answer
        session["math_problem"] = math_problem
        return math_problem

    def _new_embed_math_problem(uname: Username) -> tuple[str, str]:
        math_problem, math_answer = _new_math_problem()
        nonce = secrets.token_urlsafe(16)
        answer_signature = _embed_captcha_answer_signature(
            uname.username,
            uname.user_id,
            nonce,
            math_problem,
            math_answer,
        )
        token = _embed_captcha_serializer().dumps(
            {
                "v": 1,
                "username": uname.username,
                "user_id": uname.user_id,
                "nonce": nonce,
                "math_problem": math_problem,
                "answer_signature": answer_signature,
            }
        )
        return math_problem, token

    def _validate_embed_captcha(uname: Username, captcha_answer: str, captcha_token: str) -> bool:
        if not captcha_answer.isdigit():
            flash("⛔️ Incorrect CAPTCHA. Please enter a valid number.", "error")
            return False

        try:
            payload: dict[str, Any] = _embed_captcha_serializer().loads(
                captcha_token,
                max_age=EMBED_CAPTCHA_MAX_AGE_SECONDS,
            )
        except SignatureExpired:
            flash("⛔️ CAPTCHA expired. Please try again.", "error")
            return False
        except BadData:
            flash("⛔️ Incorrect CAPTCHA. Please try again.", "error")
            return False

        if (
            payload.get("v") != 1
            or payload.get("username") != uname.username
            or payload.get("user_id") != uname.user_id
        ):
            flash("⛔️ Incorrect CAPTCHA. Please try again.", "error")
            return False

        nonce = str(payload.get("nonce", ""))
        math_problem = str(payload.get("math_problem", ""))
        answer_signature = str(payload.get("answer_signature", ""))
        expected_signature = _embed_captcha_answer_signature(
            uname.username,
            uname.user_id,
            nonce,
            math_problem,
            captcha_answer,
        )
        if not hmac.compare_digest(answer_signature, expected_signature):
            flash("⛔️ Incorrect CAPTCHA. Please try again.", "error")
            return False

        return True

    def _embed_post_origin_is_valid(uname: Username) -> bool:
        origin = request.headers.get("Origin", "").strip()
        if not origin:
            referer = request.headers.get("Referer", "").strip()
            if referer:
                parsed_referer = urlsplit(referer)
                origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}"

        if not origin or origin == "null":
            return False

        parsed_origin = urlsplit(origin)
        parsed_host = urlsplit(request.host_url)
        return (parsed_origin.scheme, parsed_origin.netloc) == (
            parsed_host.scheme,
            parsed_host.netloc,
        )

    def _message_submission_block_reason(uname: Username) -> str | None:
        if bool(getattr(uname.user, "is_suspended", False)):
            return "suspended"
        if not uname.user.message_encryption_target:
            return "missing_recipient_keys"
        return None

    def _authenticated_sender() -> User | None:
        if not session.get("is_authenticated", False):
            return None
        return get_session_user()

    def _create_initial_conversation(
        *,
        message: Message,
        sender: User,
        recipient: User,
        raw_extracted_fields: list[tuple[str, str]],
    ) -> Conversation | None:
        if sender.id == recipient.id:
            return None

        recipient_encryption_target = recipient.message_encryption_target
        if not recipient_encryption_target:
            return None

        sender_encryption_target = sender.message_encryption_target
        conversation = Conversation()
        sender_participant = ConversationParticipant()
        sender_participant.conversation = conversation
        sender_participant.user = sender
        sender_participant.has_usable_public_key = False
        recipient_participant = ConversationParticipant()
        recipient_participant.conversation = conversation
        recipient_participant.user = recipient
        recipient_participant.has_usable_public_key = True
        conversation_message = ConversationMessage()
        conversation_message.conversation = conversation
        conversation_message.sender_participant = sender_participant
        body = format_message_email_fields(raw_extracted_fields)
        if sender_encryption_target:
            try:
                encrypted_payload = encrypt_message(body, sender_encryption_target)
            except (RuntimeError, TypeError, ValueError):
                current_app.logger.warning("Failed to encrypt conversation copy for sender.")
            else:
                sender_copy = ConversationMessageCopy()
                sender_copy.recipient_participant = sender_participant
                sender_copy.encrypted_payload = encrypted_payload
                sender_participant.has_usable_public_key = True
                conversation_message.encrypted_copies.append(sender_copy)
        recipient_payload = encrypt_message(body, recipient_encryption_target)
        recipient_copy = ConversationMessageCopy()
        recipient_copy.recipient_participant = recipient_participant
        recipient_copy.encrypted_payload = recipient_payload
        conversation_message.encrypted_copies.append(recipient_copy)
        message.conversation = conversation
        db.session.add(conversation)
        return conversation

    @app.route("/to/<username>", methods=["GET", "POST"])
    def profile(username: str) -> Response | str | tuple[str, int]:
        try:
            uname = db.session.scalars(
                db.select(Username).where(func.lower(Username._username) == username.lower())
            ).one_or_none()
        except MultipleResultsFound:
            current_app.logger.error(
                "Multiple usernames matched case-insensitive profile lookup",
                extra={"username": username.lower()},
            )
            abort(404)
        if not uname:
            abort(404)

        is_embedded = request.endpoint in {"embed_profile", "embed_profile_legacy"}
        if is_embedded:
            if not uname.embed_is_eligible or _message_submission_block_reason(uname):
                abort(404)
            g.embed_frame_ancestors = " ".join(
                Username.normalize_embed_allowed_origins(uname.embed_allowed_origins or [])
            )

        uname.create_default_field_defs()

        dynamic_form = DynamicMessageForm([x for x in uname.message_fields if x.enabled])
        form = dynamic_form.form(csrf_enabled=False if is_embedded else None)

        embed_captcha_token = None
        if is_embedded:
            math_problem, embed_captcha_token = _new_embed_math_problem(uname)
        else:
            math_problem = _get_session_math_problem(force_new=request.method == "GET")

        profile_header = safe_render_template(
            OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE),
            {
                "display_name_or_username": uname.display_name or uname.username,
                "display_name": uname.display_name,
                "username": uname.username,
            },
        )

        def _render_profile(status_code: int | None = None) -> Response | str | tuple[str, int]:
            message_submission_block_reason = _message_submission_block_reason(uname)
            owner_guard_nonce = secrets.token_urlsafe(16)
            owner_guard_signature = _owner_guard_signature(
                uname.username,
                uname.user_id,
                owner_guard_nonce,
            )
            rendered = render_template(
                "embed_profile.html" if is_embedded else "profile.html",
                profile_header=profile_header,
                form=form,
                user=uname.user,
                username=uname,
                field_data=dynamic_form.field_data(),
                display_name_or_username=uname.display_name or uname.username,
                show_caution_badge=show_directory_caution_badge(
                    uname.display_name or uname.username,
                    is_admin=uname.user.is_admin,
                    is_verified=uname.is_verified,
                    is_cautious=bool(getattr(uname.user, "is_cautious", False)),
                ),
                current_user_id=session.get("user_id"),
                recipient_public_keys=uname.user.message_recipient_keys,
                recipient_public_key_entries=(
                    notification_recipient_public_key_entries(uname.user)
                    if (
                        uname.user.enable_email_notifications
                        and uname.user.email_include_message_content
                        and not uname.user.email_encrypt_entire_body
                    )
                    else []
                ),
                math_problem=math_problem,
                message_submission_block_reason=message_submission_block_reason,
                owner_guard_nonce=owner_guard_nonce,
                owner_guard_signature=owner_guard_signature,
                is_embedded=is_embedded,
                embed_captcha_token=embed_captcha_token,
                embed_allowed_origins=(
                    Username.normalize_embed_allowed_origins(uname.embed_allowed_origins or [])
                    if is_embedded
                    else []
                ),
            )
            if status_code is None:
                return rendered
            return rendered, status_code

        if request.method == "POST":
            current_app.logger.debug("Profile form submitted.")
            if is_embedded and _message_submission_block_reason(uname):
                g.embed_frame_ancestors = "'none'"
                abort(404)

            embed_rate_limit_result = None
            if is_embedded:
                if not _embed_post_origin_is_valid(uname):
                    flash("⛔️ Invalid embed request origin. Please reload.")
                    return _render_profile(400)

                embed_rate_limit_result = check_embed_rate_limit(uname)
                emit_embed_abuse_counter(
                    EMBED_SUBMISSION_ATTEMPT_COUNTER,
                    profile_hash=embed_rate_limit_result.profile_hash,
                    source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                )
                if embed_rate_limit_result.limited:
                    emit_embed_abuse_counter(
                        EMBED_SUBMISSION_RATE_LIMITED_COUNTER,
                        profile_hash=embed_rate_limit_result.profile_hash,
                        source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                        limited_scopes=embed_rate_limit_result.limited_scopes,
                    )
                    flash("⛔️ Too many embedded submission attempts. Please try again later.")
                    return _render_profile(429)

            owner_guard_nonce = (form.owner_guard_nonce.data or "").strip()
            owner_guard_signature = (form.owner_guard_signature.data or "").strip()
            expected_signature = _owner_guard_signature(
                uname.username,
                uname.user_id,
                owner_guard_nonce,
            )
            if (
                not owner_guard_nonce
                or not owner_guard_signature
                or not hmac.compare_digest(owner_guard_signature, expected_signature)
            ):
                if embed_rate_limit_result is not None:
                    emit_embed_abuse_counter(
                        EMBED_SUBMISSION_REJECTED_COUNTER,
                        profile_hash=embed_rate_limit_result.profile_hash,
                        source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                        reason="owner_guard",
                    )
                flash("⛔️ This tip line changed while you were composing. Please reload.")
                return _render_profile(400)

            if is_embedded and not hmac.compare_digest(
                request.form.get("csrf_token", ""),
                form.embed_captcha_token.data or "",
            ):
                if embed_rate_limit_result is not None:
                    emit_embed_abuse_counter(
                        EMBED_SUBMISSION_REJECTED_COUNTER,
                        profile_hash=embed_rate_limit_result.profile_hash,
                        source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                        reason="form_token",
                    )
                flash("⛔️ Invalid embed form token. Please reload.")
                return _render_profile(400)

            block_reason = _message_submission_block_reason(uname)
            if block_reason == "suspended":
                if embed_rate_limit_result is not None:
                    emit_embed_abuse_counter(
                        EMBED_SUBMISSION_REJECTED_COUNTER,
                        profile_hash=embed_rate_limit_result.profile_hash,
                        source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                        reason="suspended",
                    )
                flash("⛔️ This account is suspended. New messages cannot be sent at this time.")
                return _render_profile(400)

            if form.validate_on_submit():
                if block_reason == "missing_recipient_keys":
                    if embed_rate_limit_result is not None:
                        emit_embed_abuse_counter(
                            EMBED_SUBMISSION_REJECTED_COUNTER,
                            profile_hash=embed_rate_limit_result.profile_hash,
                            source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                            reason="missing_recipient_keys",
                        )
                    flash(
                        (
                            "⛔️ You cannot submit messages to users who do not have any "
                            "usable recipient PGP keys."
                        ),
                        "error",
                    )
                    return _render_profile(400)

                captcha_answer = form.captcha_answer.data or ""
                captcha_valid = (
                    _validate_embed_captcha(
                        uname,
                        captcha_answer,
                        form.embed_captcha_token.data or "",
                    )
                    if is_embedded
                    else validate_captcha(captcha_answer)
                )
                if not captcha_valid:
                    if embed_rate_limit_result is not None:
                        emit_embed_abuse_counter(
                            EMBED_SUBMISSION_REJECTED_COUNTER,
                            profile_hash=embed_rate_limit_result.profile_hash,
                            source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                            reason="captcha",
                        )
                    flash("⛔️ Invalid CAPTCHA answer.", "error")
                    return _render_profile(400)

                # Create a message
                message = Message(username_id=uname.id)
                db.session.add(message)
                db.session.flush()

                extracted_fields = []
                raw_extracted_fields = []
                raw_email_field_data = []
                # Add the field values
                for data in dynamic_form.field_data():
                    field_name: str = data["name"]  # type: ignore
                    field_definition: FieldDefinition = data["field"]  # type: ignore
                    value = getattr(form, field_name).data
                    raw_value = "\n".join(value) if isinstance(value, list) else (value or "")
                    raw_extracted_fields.append((field_definition.label, str(raw_value)))
                    raw_email_field_data.append(
                        (
                            field_name,
                            field_definition.label,
                            str(raw_value),
                            field_definition.encrypted,
                        )
                    )
                    field_value = FieldValue(
                        field_definition,
                        message,
                        value,
                        field_definition.encrypted,
                    )
                    db.session.add(field_value)
                    db.session.flush()
                    extracted_fields.append((field_definition.label, field_value.value or ""))

                conversation = None
                sender = _authenticated_sender()
                if sender:
                    conversation = _create_initial_conversation(
                        message=message,
                        sender=sender,
                        recipient=uname.user,
                        raw_extracted_fields=raw_extracted_fields,
                    )

                db.session.commit()

                plaintext_new_message_body = (
                    "You have a new Hush Line message! Please log in to read it."
                )
                if uname.user.enable_email_notifications:
                    notification_encryption_target = notification_email_encryption_target(
                        uname.user
                    )
                    email_body_sent = False
                    if uname.user.email_include_message_content:
                        if uname.user.email_encrypt_entire_body:
                            encrypted_email_body = (form.encrypted_email_body.data or "").strip()
                            client_body_is_armored = _is_armored_pgp_message(encrypted_email_body)
                            can_trust_client_encrypted_body = client_body_is_armored and isinstance(
                                notification_encryption_target, str
                            )
                            if can_trust_client_encrypted_body:
                                email_body = encrypted_email_body
                                current_app.logger.debug("Sending email with encrypted body")
                            else:
                                fallback_body = format_full_message_email_body(raw_extracted_fields)
                                try:
                                    if fallback_body and notification_encryption_target:
                                        email_body = encrypt_message(
                                            fallback_body, notification_encryption_target
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
                        elif len(uname.user.enabled_notification_recipients) > 1:
                            # Keep the existing field-level email behavior
                            # when full-body encryption is disabled.
                            client_fields_by_recipient = (
                                _client_encrypted_email_fields_by_recipient(
                                    form.encrypted_email_fields_by_recipient.data or ""
                                )
                            )

                            def email_body_for_recipient(
                                recipient: NotificationRecipient,
                            ) -> str:
                                rendered_fields: list[tuple[str, str]] = []
                                for (
                                    field_name,
                                    label,
                                    raw_value,
                                    encrypted,
                                ) in raw_email_field_data:
                                    value_for_email = raw_value
                                    if encrypted:
                                        recipient_fields = client_fields_by_recipient.get(
                                            recipient.id or -1, {}
                                        )
                                        client_encrypted_value = recipient_fields.get(field_name)
                                        if client_encrypted_value:
                                            value_for_email = client_encrypted_value
                                        elif raw_value:
                                            current_app.logger.warning(
                                                "Missing recipient field ciphertext; "
                                                "sending generic notification body."
                                            )
                                            return plaintext_new_message_body
                                    rendered_fields.append((label, value_for_email))
                                return format_message_email_fields(rendered_fields)

                            send_email_to_user_recipients(
                                uname.user,
                                "New Hush Line Message Received",
                                email_body_for_recipient,
                            )
                            email_body_sent = True
                            current_app.logger.debug(
                                "Sending field-level email bodies per notification recipient"
                            )
                        else:
                            email_body = format_message_email_fields(extracted_fields)
                            current_app.logger.debug("Sending email with unencrypted body")
                    else:
                        email_body = plaintext_new_message_body
                        current_app.logger.debug("Sending email with generic body")

                    if not email_body_sent:
                        do_send_email(uname.user, email_body.strip())

                if is_embedded:
                    if embed_rate_limit_result is not None:
                        emit_embed_abuse_counter(
                            EMBED_SUBMISSION_ACCEPTED_COUNTER,
                            profile_hash=embed_rate_limit_result.profile_hash,
                            source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                        )
                    reply_url = canonical_external_url("message_reply", slug=message.reply_slug)
                    return render_template(
                        "submission_success.html",
                        message=message,
                        reply_url=reply_url,
                    )

                flash("👍 Message submitted successfully.")
                if conversation is not None:
                    current_app.logger.debug("Message sent and now redirecting to conversation")
                    return redirect(url_for("conversation", conversation_id=conversation.id))
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

            error_message = (
                "⛔️ There was an error submitting your message: " + "; ".join(errors) + "."
            )
            if embed_rate_limit_result is not None:
                emit_embed_abuse_counter(
                    EMBED_SUBMISSION_REJECTED_COUNTER,
                    profile_hash=embed_rate_limit_result.profile_hash,
                    source_bucket_hash=embed_rate_limit_result.source_bucket_hash,
                    reason="validation",
                )
            flash(error_message, "error")
            return _render_profile(400)

        return _render_profile()

    app.add_url_rule(
        "/embed/to/<username>",
        endpoint="embed_profile",
        view_func=profile,
        methods=["GET", "POST"],
    )

    app.add_url_rule(
        "/embed/<username>",
        endpoint="embed_profile_legacy",
        view_func=profile,
        methods=["GET", "POST"],
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

        reply_url = canonical_external_url("message_reply", slug=msg.reply_slug)
        return render_template("submission_success.html", message=msg, reply_url=reply_url)
