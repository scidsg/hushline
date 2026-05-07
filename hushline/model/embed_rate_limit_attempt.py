from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class EmbedRateLimitAttempt(Model):
    __tablename__ = "embed_rate_limit_attempts"

    DIGEST_LENGTH = 64
    SCOPE_LENGTH = 20

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    scope: Mapped[str] = mapped_column(db.String(SCOPE_LENGTH), nullable=False)
    bucket_hash: Mapped[str] = mapped_column(db.String(DIGEST_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now, nullable=False)

    __table_args__ = (
        Index(
            "idx_embed_rate_limit_attempts_scope_bucket_created",
            "scope",
            "bucket_hash",
            "created_at",
        ),
        Index("idx_embed_rate_limit_attempts_created", "created_at"),
    )

    def __init__(self, scope: str, bucket_hash: str, **kwargs: Any) -> None:
        super().__init__(
            scope=scope,  # type: ignore[call-arg]
            bucket_hash=bucket_hash,  # type: ignore[call-arg]
            **kwargs,
        )
