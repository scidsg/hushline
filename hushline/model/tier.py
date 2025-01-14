from typing import TYPE_CHECKING, Optional, Self

from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class Tier(Model):
    """User (payment) tier"""

    __tablename__ = "tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), unique=True)
    monthly_amount: Mapped[int] = mapped_column(db.Integer)  # in cents USD
    stripe_product_id: Mapped[Optional[str]] = mapped_column(db.String(255), unique=True)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(db.String(255), unique=True)

    def __init__(self, name: str, monthly_amount: int) -> None:
        super().__init__()
        self.name = name
        self.monthly_amount = monthly_amount

    @staticmethod
    def free_tier_id() -> int:
        return 1

    @staticmethod
    def business_tier_id() -> int:
        return 2

    @staticmethod
    def free_tier() -> Self | None:  # type: ignore
        return db.session.get(Tier, Tier.free_tier_id())  # type: ignore

    @staticmethod
    def business_tier() -> Self | None:  # type: ignore
        return db.session.get(Tier, Tier.business_tier_id())  # type: ignore
