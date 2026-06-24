import json
from dataclasses import dataclass
from typing import cast

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
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
    ChatKey,
    FieldDefinition,
    FieldValue,
    Message,
    NotificationRecipient,
    User,
)
from hushline.routes.common import do_send_email

BROADCAST_SEND_SUBMIT = "send_broadcast"


class AdminBroadcastForm(FlaskForm):
    encrypted_payloads = HiddenField("Encrypted payloads")
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
    def chat_only_users(self) -> list[User]:
        return [
            user
            for user in self.target_users
            if user.active_chat_key is not None and not user.message_encryption_target
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


def _active_chat_key_exists() -> ColumnElement[bool]:
    return cast(
        ColumnElement[bool],
        exists().where(and_(ChatKey.user_id == User.id, ChatKey.disabled_at.is_(None))),
    )


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
    has_chat_key = _active_chat_key_exists()
    return and_(User.is_suspended.is_(False), or_(has_pgp_key, has_recipient_pgp_key, has_chat_key))


def _load_audience() -> BroadcastAudience:
    users = list(
        db.session.scalars(
            db.select(User)
            .where(_audience_predicate())
            .options(
                selectinload(User.notification_recipients),
                selectinload(User.chat_keys),
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
    submitted_user_ids: set[int] = set()
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
        submitted_user_ids.add(user.id)

    if submitted_count:
        db.session.commit()

    notification_body = "You have a new Hush Line message! Please log in to read it."
    for user in users:
        if user.id in submitted_user_ids:
            do_send_email(user, notification_body)

    return submitted_count


def register_broadcast_routes(bp: Blueprint) -> None:
    @bp.route("/broadcasts", methods=["GET", "POST"])
    @admin_authentication_required
    def broadcasts() -> tuple[str, int] | Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        form = AdminBroadcastForm()
        status_code = 200
        audience = _load_audience()

        if request.method == "POST":
            if form.validate():
                if BROADCAST_SEND_SUBMIT in request.form:
                    if not form.confirm_send.data:
                        form.confirm_send.errors.append(
                            "Confirm before submitting these encrypted messages."
                        )
                        status_code = 400
                    elif not audience.encrypted_submission_users:
                        flash(
                            "No eligible encrypted message recipients match this audience.",
                            "error",
                        )
                        status_code = 400
                    else:
                        encrypted_payloads = _encrypted_payloads_by_user(
                            form.encrypted_payloads.data or ""
                        )
                        expected_user_ids = {
                            user.id for user in audience.encrypted_submission_users
                        }
                        if set(encrypted_payloads) != expected_user_ids:
                            form.encrypted_payloads.errors.append(
                                "Encrypted payloads are missing or incomplete."
                            )
                            status_code = 400
                        else:
                            try:
                                submitted_count = _submit_encrypted_broadcast_messages(
                                    audience.encrypted_submission_users,
                                    encrypted_payloads,
                                )
                            except ValueError:
                                db.session.rollback()
                                form.encrypted_payloads.errors.append(
                                    "One or more recipients became ineligible before submission."
                                )
                                status_code = 400
                                return render_template(
                                    "settings/broadcasts.html",
                                    user=user,
                                    form=form,
                                    audience=audience,
                                    encryption_recipients=audience.encryption_recipients,
                                ), status_code
                            flash(
                                f"Encrypted messages submitted to {submitted_count} users.",
                                "success",
                            )
                            return redirect(url_for(".broadcasts"))
            else:
                status_code = 400

        return render_template(
            "settings/broadcasts.html",
            user=user,
            form=form,
            audience=audience,
            encryption_recipients=audience.encryption_recipients,
        ), status_code
