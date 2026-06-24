import json
from dataclasses import dataclass
from typing import cast

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement
from werkzeug.wrappers.response import Response
from wtforms import BooleanField, HiddenField, SubmitField

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.forms import Button
from hushline.model import (
    FieldDefinition,
    FieldValue,
    Message,
    NotificationRecipient,
    User,
)
from hushline.routes.common import do_send_email

BROADCAST_SEND_SUBMIT = "send_broadcast"
BROADCAST_CHUNK_FIELD = "broadcast_chunk"
BROADCAST_COMPLETED_IDS_FIELD = "broadcast_completed_user_ids"
BROADCAST_EXPECTED_IDS_FIELD = "broadcast_expected_user_ids"
BROADCAST_FINAL_CHUNK_FIELD = "broadcast_final_chunk"


class AdminBroadcastForm(FlaskForm):
    encrypted_payloads = HiddenField("Encrypted payloads")
    encryption_failures = HiddenField("Encryption failures")
    confirm_send = BooleanField(
        "I understand this will create encrypted inbox submissions for all eligible users above."
    )
    send = SubmitField("Submit Messages", name=BROADCAST_SEND_SUBMIT, widget=Button())


@dataclass(frozen=True)
class BroadcastAudience:
    target_users: list[User]

    @property
    def encrypted_submission_users(self) -> list[User]:
        return [
            user
            for user in self.target_users
            if user.primary_username is not None
            and user.message_encryption_target
            and _message_field_for(user) is not None
        ]

    @property
    def notification_email_count(self) -> int:
        return sum(_unique_enabled_email_count(user) for user in self.encrypted_submission_users)

    @property
    def encryption_recipients(self) -> list[dict[str, object]]:
        recipients: list[dict[str, object]] = []
        for user in self.encrypted_submission_users:
            username = user.primary_username
            if username is None:
                continue
            username.create_default_field_defs()
            keys = user.message_recipient_keys
            if not keys:
                continue
            recipients.append(
                {
                    "user_id": user.id,
                    "username_id": username.id,
                    "public_keys": keys,
                }
            )
        return recipients


def _recipient_pgp_key_exists() -> ColumnElement[bool]:
    return cast(
        ColumnElement[bool],
        exists().where(
            and_(
                NotificationRecipient.user_id == User.id,
                NotificationRecipient.enabled.is_(True),
                NotificationRecipient._pgp_key.is_not(None),
            )
        ),
    )


def _audience_predicate() -> ColumnElement[bool]:
    has_pgp_key = User._pgp_key.is_not(None)
    has_recipient_pgp_key = _recipient_pgp_key_exists()
    return and_(User.is_suspended.is_(False), or_(has_pgp_key, has_recipient_pgp_key))


def _load_audience() -> BroadcastAudience:
    users = list(
        db.session.scalars(
            db.select(User)
            .where(_audience_predicate())
            .options(
                selectinload(User.notification_recipients),
                selectinload(User.primary_username),
            )
            .order_by(User.id)
        ).all()
    )
    return BroadcastAudience(target_users=users)


def _unique_enabled_email_count(user: User) -> int:
    emails = {
        (recipient.email or "").strip().casefold()
        for recipient in user.enabled_notification_recipients
        if recipient.email
    }
    return len(emails)


def _is_armored_pgp_message(value: object) -> bool:
    return (
        isinstance(value, str)
        and "-----BEGIN PGP MESSAGE-----" in value
        and "-----END PGP MESSAGE-----" in value
    )


def _encrypted_payloads_by_user(raw_payloads: str) -> dict[int, str]:
    try:
        payloads = json.loads(raw_payloads)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payloads, dict):
        return {}

    encrypted_payloads: dict[int, str] = {}
    for user_id, payload in payloads.items():
        try:
            parsed_user_id = int(user_id)
        except (TypeError, ValueError):
            continue
        if _is_armored_pgp_message(payload):
            encrypted_payloads[parsed_user_id] = payload
    return encrypted_payloads


def _encryption_failure_user_ids(raw_failures: str) -> set[int]:
    return _user_ids_from_json(raw_failures)


def _user_ids_from_json(raw_user_ids: str) -> set[int]:
    try:
        user_ids = json.loads(raw_user_ids)
    except json.JSONDecodeError:
        return set()
    if not isinstance(user_ids, list):
        return set()

    parsed_user_ids: set[int] = set()
    for user_id in user_ids:
        try:
            parsed_user_ids.add(int(user_id))
        except (TypeError, ValueError):
            continue
    return parsed_user_ids


def _message_field_for(user: User) -> FieldDefinition | None:
    username = user.primary_username
    if username is None:
        return None
    username.create_default_field_defs()
    enabled_fields = [field for field in username.message_fields if field.enabled]
    message_fields = [field for field in enabled_fields if field.label.casefold() == "message"]
    return (message_fields or enabled_fields)[-1] if enabled_fields else None


def _submit_encrypted_broadcast_messages(
    users: list[User], encrypted_payloads: dict[int, str]
) -> int:
    submitted_count = 0
    submitted_notification_user_ids: list[int] = []
    for user in users:
        encrypted_payload = encrypted_payloads.get(user.id)
        field_definition = _message_field_for(user)
        username = user.primary_username
        if not encrypted_payload or field_definition is None or username is None:
            msg = "Encrypted broadcast target became ineligible before submission."
            raise ValueError(msg)

        message = Message(username_id=username.id)
        db.session.add(message)
        db.session.flush()
        db.session.add(FieldValue(field_definition, message, encrypted_payload, True))
        submitted_count += 1
        submitted_notification_user_ids.append(user.id)

    if submitted_count:
        db.session.commit()
        _send_broadcast_notification_emails(tuple(submitted_notification_user_ids))

    return submitted_count


def _send_broadcast_notification_emails(user_ids: tuple[int, ...]) -> None:
    notification_body = "You have a new Hush Line message! Please log in to read it."
    users = list(
        db.session.scalars(
            db.select(User)
            .where(User.id.in_(user_ids))
            .options(selectinload(User.notification_recipients))
            .order_by(User.id)
        ).all()
    )
    for user in users:
        do_send_email(user, notification_body)


def _json_broadcast_error(message: str) -> tuple[Response, int]:
    return jsonify({"error": message}), 400


def register_broadcast_routes(bp: Blueprint) -> None:
    @bp.route("/broadcasts", methods=["GET", "POST"])
    @admin_authentication_required
    def broadcasts() -> tuple[str, int] | tuple[Response, int] | Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        form = AdminBroadcastForm()
        status_code = 200
        audience = _load_audience()

        if request.method == "POST":
            chunked_broadcast = request.form.get(BROADCAST_CHUNK_FIELD) == "1"
            if form.validate():
                if BROADCAST_SEND_SUBMIT in request.form:
                    if not form.confirm_send.data:
                        if chunked_broadcast:
                            return _json_broadcast_error(
                                "Confirm before submitting these encrypted messages."
                            )
                        form.confirm_send.errors.append(
                            "Confirm before submitting these encrypted messages."
                        )
                        status_code = 400
                    elif not audience.encrypted_submission_users:
                        if chunked_broadcast:
                            return _json_broadcast_error(
                                "No eligible encrypted message recipients match this audience."
                            )
                        flash(
                            "No eligible encrypted message recipients match this audience.",
                            "error",
                        )
                        status_code = 400
                    else:
                        encrypted_payloads = _encrypted_payloads_by_user(
                            form.encrypted_payloads.data or ""
                        )
                        failed_user_ids = _encryption_failure_user_ids(
                            form.encryption_failures.data or ""
                        )
                        expected_user_ids = {
                            user.id for user in audience.encrypted_submission_users
                        }
                        submitted_user_ids = set(encrypted_payloads)
                        expected_chunk_user_ids = _user_ids_from_json(
                            request.form.get(BROADCAST_EXPECTED_IDS_FIELD, "")
                        )
                        completed_chunk_user_ids = _user_ids_from_json(
                            request.form.get(BROADCAST_COMPLETED_IDS_FIELD, "")
                        )
                        final_chunk = request.form.get(BROADCAST_FINAL_CHUNK_FIELD) == "1"
                        if not submitted_user_ids and not (chunked_broadcast and failed_user_ids):
                            if chunked_broadcast:
                                return _json_broadcast_error(
                                    "No recipient messages could be encrypted."
                                )
                            form.encrypted_payloads.errors.append(
                                "No recipient messages could be encrypted."
                            )
                            status_code = 400
                        elif submitted_user_ids & failed_user_ids:
                            if chunked_broadcast:
                                return _json_broadcast_error(
                                    "Encrypted payloads conflict with reported encryption failures."
                                )
                            form.encrypted_payloads.errors.append(
                                "Encrypted payloads conflict with reported encryption failures."
                            )
                            status_code = 400
                        elif chunked_broadcast and expected_chunk_user_ids != expected_user_ids:
                            return _json_broadcast_error(
                                "Broadcast audience changed. Refresh and try again."
                            )
                        elif not (submitted_user_ids | failed_user_ids).issubset(expected_user_ids):
                            if chunked_broadcast:
                                return _json_broadcast_error(
                                    "Encrypted payloads include unknown recipients."
                                )
                            form.encrypted_payloads.errors.append(
                                "Encrypted payloads include unknown recipients."
                            )
                            status_code = 400
                        elif chunked_broadcast and not completed_chunk_user_ids.issubset(
                            expected_user_ids
                        ):
                            return _json_broadcast_error(
                                "Broadcast completion includes unknown recipients."
                            )
                        elif chunked_broadcast and not (
                            submitted_user_ids | failed_user_ids
                        ).issubset(completed_chunk_user_ids):
                            return _json_broadcast_error(
                                "Broadcast completion is missing submitted recipients."
                            )
                        elif (
                            chunked_broadcast
                            and final_chunk
                            and completed_chunk_user_ids != expected_user_ids
                        ):
                            return _json_broadcast_error(
                                "Broadcast batches are incomplete. Refresh and try again."
                            )
                        elif (
                            not chunked_broadcast
                            and submitted_user_ids | failed_user_ids != expected_user_ids
                        ):
                            form.encrypted_payloads.errors.append(
                                "Encrypted payloads are missing or incomplete."
                            )
                            status_code = 400
                        else:
                            submitted_users = [
                                user
                                for user in audience.encrypted_submission_users
                                if user.id in submitted_user_ids
                            ]
                            try:
                                submitted_count = _submit_encrypted_broadcast_messages(
                                    submitted_users,
                                    encrypted_payloads,
                                )
                            except ValueError:
                                db.session.rollback()
                                form.encrypted_payloads.errors.append(
                                    "One or more recipients became ineligible before submission."
                                )
                                status_code = 400
                                if chunked_broadcast:
                                    return _json_broadcast_error(
                                        "One or more recipients became ineligible "
                                        "before submission."
                                    )
                                return render_template(
                                    "settings/broadcasts.html",
                                    user=user,
                                    form=form,
                                    audience=audience,
                                    encryption_recipients=audience.encryption_recipients,
                                ), status_code
                            skipped_count = len(failed_user_ids)
                            if chunked_broadcast:
                                return jsonify(
                                    {
                                        "submitted_count": submitted_count,
                                        "skipped_count": skipped_count,
                                    }
                                )
                            if skipped_count:
                                flash(
                                    (
                                        "Encrypted messages submitted to "
                                        f"{submitted_count} users. Skipped {skipped_count} "
                                        "users whose keys could not be used in this browser."
                                    ),
                                    "warning",
                                )
                            else:
                                flash(
                                    f"Encrypted messages submitted to {submitted_count} users.",
                                    "success",
                                )
                            return redirect(url_for(".broadcasts"))
            else:
                if chunked_broadcast:
                    return _json_broadcast_error("Invalid broadcast submission.")
                status_code = 400

        return render_template(
            "settings/broadcasts.html",
            user=user,
            form=form,
            audience=audience,
            encryption_recipients=audience.encryption_recipients,
        ), status_code
