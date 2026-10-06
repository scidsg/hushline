"""Account ownership and durable cancellation intent; no payment credentials."""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class SingleTenantOrder(Model):
    __tablename__ = "single_tenant_orders"

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True
    )
    owner_ref: Mapped[str] = mapped_column(db.String(64), unique=True, nullable=False)
    license_limit: Mapped[int | None] = mapped_column(db.Integer)
    stage: Mapped[str] = mapped_column(db.String(32), default="licenses", nullable=False)
    service_state: Mapped[str] = mapped_column(db.String(32), default="unpaid", nullable=False)
    domain: Mapped[str] = mapped_column(db.String(253), default="", nullable=False)
    paid: Mapped[bool] = mapped_column(default=False, nullable=False)
    cancelled: Mapped[bool] = mapped_column(default=False, nullable=False)
    cancellation_pending: Mapped[bool] = mapped_column(default=False, nullable=False)
    period_end: Mapped[str | None] = mapped_column(db.String(40))
    period_start: Mapped[str | None] = mapped_column(db.String(40))
    cancelled_at: Mapped[str | None] = mapped_column(db.String(40))
    billing_receipt: Mapped[str | None] = mapped_column(db.String(32), unique=True)
    stripe_session_id: Mapped[str | None] = mapped_column(db.String(255), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(db.String(255), unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(db.String(255))
    billing_sync_pending: Mapped[bool] = mapped_column(default=False, nullable=False)

    def __init__(self, *, id: str, user_id: int, owner_ref: str) -> None:
        super().__init__()
        self.id = id
        self.user_id = user_id
        self.owner_ref = owner_ref
