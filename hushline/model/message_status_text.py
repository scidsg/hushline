from typing import TYPE_CHECKING, Optional, Self, Tuple

from flask import abort, current_app
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db
from hushline.model.enums import MessageStatus

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class MessageStatusText(Model):
    """
    The text representing a user's "response" (bulk applied) to a message for its current state
    """

    __tablename__ = "message_status_text"
    __table_args__ = (UniqueConstraint("user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    status: Mapped[MessageStatus] = mapped_column(SQLAlchemyEnum(MessageStatus))
    markdown: Mapped[str] = mapped_column()

    @classmethod
    def statuses_for_user(cls, user_id: int) -> list[Tuple[MessageStatus, Optional[Self]]]:
        statuses = {
            x.status: x
            for x in db.session.scalars(
                db.select(MessageStatusText).filter_by(user_id=user_id)
            ).all()
        }
        return [(x, statuses.get(x)) for x in MessageStatus]

    @classmethod
    def upsert(cls, user_id: int, status: MessageStatus, markdown: str) -> None:
        markdown = markdown.strip()
        if markdown:
            db.session.execute(
                insert(MessageStatusText)
                .values(user_id=user_id, status=status, markdown=markdown)
                .on_conflict_do_update(
                    constraint=f"uq_{cls.__tablename__}_user_id",
                    set_={"markdown": markdown},
                )
            )
        else:
            row_count = db.session.execute(
                db.delete(MessageStatusText).where(
                    MessageStatusText.user_id == user_id,
                    MessageStatusText.status == status,
                )
            ).rowcount
            if row_count > 1:
                current_app.logger.error(
                    f"Would have deleted multiple rows for MessageStatus user_id={user_id} "
                    f"status={status.value}"
                )
                db.session.rollback()
                abort(503)
