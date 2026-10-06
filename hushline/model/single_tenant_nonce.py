"""Replay protection for the dedicated provisioning service, without credentials."""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class SingleTenantNonce(Model):
    __tablename__ = "single_tenant_nonces"

    nonce: Mapped[str] = mapped_column(db.String(32), primary_key=True)
    seen: Mapped[int] = mapped_column(db.BigInteger, nullable=False, index=True)

    def __init__(self, *, nonce: str, seen: int) -> None:
        super().__init__()
        self.nonce = nonce
        self.seen = seen
