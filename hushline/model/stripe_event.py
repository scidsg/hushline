from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column
from stripe import Event

from hushline.db import db
from hushline.model.enums import StripeEventStatusEnum

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

else:
    Model = db.Model


class StripeEvent(Model):
    __tablename__ = "stripe_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(db.String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(db.String(255))
    event_created: Mapped[int] = mapped_column(db.Integer)
    event_data: Mapped[str] = mapped_column(db.Text)
    status: Mapped[Optional[StripeEventStatusEnum]] = mapped_column(
        SQLAlchemyEnum(StripeEventStatusEnum), default=StripeEventStatusEnum.PENDING
    )
    error_message: Mapped[Optional[str]] = mapped_column(db.Text)

    def __init__(self, event: Event, **kwargs: dict[str, Any]) -> None:
        super().__init__(**kwargs)
        self.event_id = event.id
        self.event_created = event.created
        self.event_type = event.type
        self.event_data = str(event)
