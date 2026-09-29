from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.user import User
else:
    Model = db.Model


class RecoveryCodeBatch(Model):
    __tablename__ = "recovery_code_batches"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="recovery_code_batches")
    codes: Mapped[list["RecoveryCode"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="RecoveryCode.id.asc()",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class RecoveryCode(Model):
    __tablename__ = "recovery_codes"
    __table_args__ = (
        CheckConstraint(
            "octet_length(code_hash) = 32",
            name="ck_recovery_codes_hash_length",
        ),
        Index("ix_recovery_codes_batch_consumed", "batch_id", "consumed_at"),
    )

    HASH_LENGTH = 32

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        db.ForeignKey("recovery_code_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[bytes] = mapped_column(
        db.LargeBinary(HASH_LENGTH), nullable=False, unique=True, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    batch: Mapped[RecoveryCodeBatch] = relationship(back_populates="codes")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
