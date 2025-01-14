from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column
from stripe import Invoice

from hushline.db import db
from hushline.model.enums import StripeInvoiceStatusEnum
from hushline.model.tier import Tier
from hushline.model.user import User

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class StripeInvoice(Model):
    __tablename__ = "stripe_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(db.String(255))
    invoice_id: Mapped[str] = mapped_column(db.String(255), unique=True, index=True)
    hosted_invoice_url: Mapped[str] = mapped_column(db.String(2048))
    total: Mapped[int] = mapped_column(db.Integer)
    status: Mapped[Optional[StripeInvoiceStatusEnum]] = mapped_column(
        SQLAlchemyEnum(StripeInvoiceStatusEnum)
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    tier_id: Mapped[int] = mapped_column(db.ForeignKey("tiers.id"))

    def __init__(self, invoice: Invoice) -> None:
        if invoice.id:
            self.invoice_id = invoice.id
        if invoice.customer and isinstance(invoice.customer, str):
            self.customer_id = invoice.customer
        if invoice.hosted_invoice_url:
            self.hosted_invoice_url = invoice.hosted_invoice_url
        if invoice.total:
            self.total = invoice.total
        else:
            self.total = 0
        if invoice.status:
            self.status = StripeInvoiceStatusEnum(invoice.status)
        if invoice.created:
            self.created_at = datetime.fromtimestamp(invoice.created, tz=timezone.utc)

        # Look up the user by their customer ID
        user = db.session.scalars(
            db.select(User).filter_by(stripe_customer_id=invoice.customer)
        ).one_or_none()
        if user:
            self.user_id = user.id
        else:
            raise ValueError(f"Could not find user with customer ID {invoice.customer}")

        # Look up the tier by the product_id
        if invoice.lines.data[0].plan:
            product_id = invoice.lines.data[0].plan.product

            tier = db.session.scalars(
                db.select(Tier).filter_by(stripe_product_id=product_id)
            ).one_or_none()
            if tier:
                self.tier_id = tier.id
            else:
                raise ValueError(f"Could not find tier with product ID {product_id}")
        else:
            raise ValueError("Invoice does not have a plan")
