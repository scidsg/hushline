import json

from sqlalchemy import or_

from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    FieldDefinition,
    FieldValue,
    Message,
    MessageStatusText,
    NotificationRecipient,
    StripeEvent,
    StripeEventStatusEnum,
    StripeInvoice,
    StripeInvoiceStatusEnum,
    User,
    Username,
)

DELETION_BLOCKING_STRIPE_INVOICE_STATUSES = {
    StripeInvoiceStatusEnum.DRAFT,
    StripeInvoiceStatusEnum.OPEN,
}
DELETION_BLOCKING_STRIPE_INVOICE_EVENT_STATUSES = {
    StripeEventStatusEnum.PENDING,
    StripeEventStatusEnum.IN_PROGRESS,
}
DELETION_BLOCKING_STRIPE_INVOICE_EVENT_TYPES = {
    "invoice.updated",
    "invoice.payment_succeeded",
}
STRIPE_INVOICE_EVENT_SCRUB_TYPES = {
    "invoice.created",
    *DELETION_BLOCKING_STRIPE_INVOICE_EVENT_TYPES,
}
REDACTED_STRIPE_EVENT_DATA = "{}"


def stripe_invoice_counts_by_user_ids(user_ids: set[int]) -> dict[int, int]:
    if not user_ids:
        return {}

    return {
        user_id: invoice_count
        for user_id, invoice_count in db.session.execute(
            db.select(StripeInvoice.user_id, db.func.count(StripeInvoice.id))
            .where(StripeInvoice.user_id.in_(user_ids))
            .group_by(StripeInvoice.user_id)
        )
    }


def deletion_blocking_stripe_invoice_counts_by_user_ids(user_ids: set[int]) -> dict[int, int]:
    if not user_ids:
        return {}

    return {
        user_id: invoice_count
        for user_id, invoice_count in db.session.execute(
            db.select(StripeInvoice.user_id, db.func.count(StripeInvoice.id))
            .where(StripeInvoice.user_id.in_(user_ids))
            .where(
                or_(
                    StripeInvoice.status.is_(None),
                    StripeInvoice.status.in_(DELETION_BLOCKING_STRIPE_INVOICE_STATUSES),
                )
            )
            .group_by(StripeInvoice.user_id)
        )
    }


def _invoice_id_from_stripe_event_data(event_data: str) -> str | None:
    try:
        event = json.loads(event_data)
    except json.JSONDecodeError:
        return None

    event_object = event.get("data", {}).get("object", {})
    invoice_id = event_object.get("id")
    if isinstance(invoice_id, str):
        return invoice_id

    return None


def deletion_blocking_stripe_invoice_event_counts_by_user_ids(
    user_ids: set[int],
) -> dict[int, int]:
    if not user_ids:
        return {}

    invoice_users_by_invoice_id = {
        invoice_id: user_id
        for user_id, invoice_id in db.session.execute(
            db.select(StripeInvoice.user_id, StripeInvoice.invoice_id).where(
                StripeInvoice.user_id.in_(user_ids)
            )
        )
    }
    if not invoice_users_by_invoice_id:
        return {}

    counts_by_user_id: dict[int, int] = {}
    event_data_rows = db.session.scalars(
        db.select(StripeEvent.event_data)
        .where(StripeEvent.event_type.in_(DELETION_BLOCKING_STRIPE_INVOICE_EVENT_TYPES))
        .where(StripeEvent.status.in_(DELETION_BLOCKING_STRIPE_INVOICE_EVENT_STATUSES))
    )
    for event_data in event_data_rows:
        invoice_id = _invoice_id_from_stripe_event_data(event_data)
        if invoice_id is None:
            continue

        user_id = invoice_users_by_invoice_id.get(invoice_id)
        if user_id is None:
            continue

        counts_by_user_id[user_id] = counts_by_user_id.get(user_id, 0) + 1

    return counts_by_user_id


def has_deletion_blocking_stripe_invoice(user: User) -> bool:
    if user.id is None:
        return False

    return bool(deletion_blocking_stripe_invoice_counts_by_user_ids({user.id}).get(user.id, 0))


def has_deletion_blocking_stripe_invoice_event(user: User) -> bool:
    if user.id is None:
        return False

    return bool(
        deletion_blocking_stripe_invoice_event_counts_by_user_ids({user.id}).get(user.id, 0)
    )


def _redact_processed_stripe_invoice_events(invoice_ids: set[str]) -> None:
    if not invoice_ids:
        return

    events = db.session.scalars(
        db.select(StripeEvent)
        .where(StripeEvent.event_type.in_(STRIPE_INVOICE_EVENT_SCRUB_TYPES))
        .where(~StripeEvent.status.in_(DELETION_BLOCKING_STRIPE_INVOICE_EVENT_STATUSES))
    )
    for event in events:
        invoice_id = _invoice_id_from_stripe_event_data(event.event_data)
        if invoice_id in invoice_ids:
            event.event_data = REDACTED_STRIPE_EVENT_DATA


def delete_user_and_related(user: User) -> None:
    # Delete field values and definitions
    usernames = db.session.scalars(db.select(Username).filter_by(user_id=user.id)).all()
    username_ids = [username.id for username in usernames]
    stripe_invoice_ids = set(
        db.session.scalars(db.select(StripeInvoice.invoice_id).filter_by(user_id=user.id)).all()
    )

    # Delete all FieldValue entries related to the user's usernames
    db.session.execute(
        db.delete(FieldValue).where(
            FieldValue.field_definition_id.in_(
                db.select(FieldDefinition.id).where(FieldDefinition.username_id.in_(username_ids))
            )
        )
    )

    # Delete all FieldDefinition entries related to the user's usernames
    db.session.execute(
        db.delete(FieldDefinition).where(FieldDefinition.username_id.in_(username_ids))
    )

    # Delete messages and related data
    db.session.execute(
        db.delete(Message).filter(
            Message.username_id.in_(db.select(Username.id).filter_by(user_id=user.id))
        )
    )
    db.session.execute(db.delete(MessageStatusText).filter_by(user_id=user.id))
    db.session.execute(db.delete(AuthenticationLog).filter_by(user_id=user.id))
    db.session.execute(db.delete(NotificationRecipient).filter_by(user_id=user.id))
    _redact_processed_stripe_invoice_events(stripe_invoice_ids)
    db.session.execute(db.delete(StripeInvoice).filter_by(user_id=user.id))

    # Delete username and finally the user
    db.session.execute(db.delete(Username).filter_by(user_id=user.id))
    db.session.delete(user)


def delete_username_and_related(username: Username) -> None:
    # Delete field values and definitions for this username
    db.session.execute(
        db.delete(FieldValue).where(
            FieldValue.field_definition_id.in_(
                db.select(FieldDefinition.id).where(FieldDefinition.username_id == username.id)
            )
        )
    )
    db.session.execute(db.delete(FieldDefinition).where(FieldDefinition.username_id == username.id))

    # Delete messages scoped to this username
    db.session.execute(db.delete(Message).filter(Message.username_id == username.id))

    # Delete the username itself
    db.session.delete(username)
