from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.user import User
else:
    Model = db.Model


class ChatKey(Model):
    __tablename__ = "chat_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key_version"),
        Index("ix_chat_keys_user_id_disabled_at", "user_id", "disabled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_version: Mapped[int] = mapped_column(nullable=False)
    public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    public_signing_key: Mapped[str | None] = mapped_column(db.Text)
    encrypted_private_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    kdf_algorithm: Mapped[str] = mapped_column(db.String(128), nullable=False)
    kdf_params: Mapped[dict[str, Any]] = mapped_column(db.JSON, nullable=False)
    kdf_salt: Mapped[str] = mapped_column(db.Text, nullable=False)
    wrapping_algorithm: Mapped[str] = mapped_column(db.String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    rotated_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    recovery_state: Mapped[str | None] = mapped_column(db.String(64))

    user: Mapped["User"] = relationship(back_populates="chat_keys")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @classmethod
    def active_for_user_id(cls, user_id: int) -> "ChatKey | None":
        return db.session.scalars(
            db.select(cls)
            .where(cls.user_id == user_id, cls.disabled_at.is_(None))
            .order_by(cls.key_version.desc())
            .limit(1)
        ).one_or_none()


class ChatAccount(Model):
    """Public, non-secret account identity metadata for versioned chat protocols."""

    __tablename__ = "chat_accounts"
    __table_args__ = (
        CheckConstraint("identity_version >= 0", name="identity_version"),
        CheckConstraint("membership_sequence >= 0", name="membership_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    public_id: Mapped[str] = mapped_column(
        db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4())
    )
    identity_version: Mapped[int] = mapped_column(
        db.BigInteger, nullable=False, default=0, server_default=text("0")
    )
    membership_sequence: Mapped[int] = mapped_column(
        db.BigInteger, nullable=False, default=0, server_default=text("0")
    )
    identity_public_key: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="chat_account")
    devices: Mapped[list["ChatDevice"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    archive_epochs: Mapped[list["ChatArchiveEpoch"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ChatDevice(Model):
    """An opaque, account-authorized browser device and membership snapshot."""

    __tablename__ = "chat_devices"
    __table_args__ = (
        UniqueConstraint("account_id", "public_id"),
        Index("ix_chat_devices_account_active", "account_id", "revoked_at", "expires_at"),
        CheckConstraint("membership_sequence > 0", name="membership_sequence"),
        CheckConstraint("key_version > 0", name="key_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    public_id: Mapped[str] = mapped_column(db.String(36), nullable=False, unique=True)
    session_id_hash: Mapped[str] = mapped_column(db.String(64), nullable=False)
    membership_sequence: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    key_version: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    membership_sha256: Mapped[str] = mapped_column(db.String(64), nullable=False)
    signing_public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    protocol_identity_public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    account_identity_public_key: Mapped[str | None] = mapped_column(db.Text)
    membership: Mapped[dict[str, Any]] = mapped_column(db.JSON, nullable=False)
    membership_signature: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    account: Mapped["ChatAccount"] = relationship(back_populates="devices")
    signed_prekeys: Mapped[list["ChatSignedPrekey"]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    one_time_prekeys: Mapped[list["ChatOneTimePrekey"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ChatOneTimePrekey.device_id",
    )
    prekey_claims: Mapped[list["ChatPrekeyClaim"]] = relationship(
        foreign_keys="ChatPrekeyClaim.claimed_by_device_id",
        back_populates="claimed_by_device",
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ChatSignedPrekey(Model):
    """A device-authenticated classical/PQ signed-prekey pair."""

    __tablename__ = "chat_signed_prekeys"
    __table_args__ = (
        UniqueConstraint("device_id", "key_id"),
        Index("ix_chat_signed_prekeys_device_active", "device_id", "retired_at", "expires_at"),
        CheckConstraint("key_id > 0", name="key_id"),
        CheckConstraint("membership_sequence > 0", name="membership_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_id: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    membership_sequence: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    classical_public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    classical_signature: Mapped[str] = mapped_column(db.Text, nullable=False)
    pq_public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    pq_signature: Mapped[str] = mapped_column(db.Text, nullable=False)
    publication_sha256: Mapped[str] = mapped_column(db.String(64), nullable=False)
    publication_signature: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    device: Mapped["ChatDevice"] = relationship(back_populates="signed_prekeys")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ChatOneTimePrekey(Model):
    """An atomic classical/PQ one-time prekey pair and its bounded tombstone."""

    __tablename__ = "chat_one_time_prekeys"
    __table_args__ = (
        UniqueConstraint("device_id", "key_id"),
        Index(
            "ix_chat_one_time_prekeys_claimable",
            "device_id",
            "consumed_at",
            "expires_at",
        ),
        Index("ix_chat_one_time_prekeys_tombstone", "tombstone_expires_at"),
        CheckConstraint("key_id > 0", name="key_id"),
        CheckConstraint("membership_sequence > 0", name="membership_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    public_id: Mapped[str] = mapped_column(
        db.String(36), nullable=False, unique=True, default=lambda: str(uuid4())
    )
    key_id: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    membership_sequence: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    classical_public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    pq_public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    pq_signature: Mapped[str] = mapped_column(db.Text, nullable=False)
    publication_signature: Mapped[str] = mapped_column(db.Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    tombstone_expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    device: Mapped["ChatDevice"] = relationship(
        back_populates="one_time_prekeys", foreign_keys=[device_id]
    )
    claims: Mapped[list["ChatPrekeyClaim"]] = relationship(
        back_populates="prekey", cascade="all, delete-orphan", passive_deletes=True
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ChatPrekeyClaim(Model):
    """A replay-stable reservation and bounded consumption tombstone."""

    __tablename__ = "chat_prekey_claims"
    __table_args__ = (
        Index("ix_chat_prekey_claims_prekey_active", "prekey_id", "reservation_expires_at"),
        Index("ix_chat_prekey_claims_tombstone", "tombstone_expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(db.String(36), nullable=False, unique=True)
    prekey_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_one_time_prekeys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claimed_by_device_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("chat_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    reservation_expires_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    tombstone_expires_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False
    )

    prekey: Mapped["ChatOneTimePrekey"] = relationship(back_populates="claims")
    claimed_by_device: Mapped["ChatDevice | None"] = relationship(
        foreign_keys=[claimed_by_device_id], back_populates="prekey_claims"
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ChatPqRateLimitAttempt(Model):
    """A privacy-minimized rate-limit event for PQ device operations."""

    __tablename__ = "chat_pq_rate_limit_attempts"
    __table_args__ = (
        Index("ix_chat_pq_rate_limit_user_action_created", "user_id", "action", "created_at"),
        Index("ix_chat_pq_rate_limit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(db.String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ChatArchiveEpoch(Model):
    """Opaque archive-key material for one account epoch."""

    __tablename__ = "chat_archive_epochs"
    __table_args__ = (
        UniqueConstraint("account_id", "epoch"),
        Index("ix_chat_archive_epochs_account_active", "account_id", "retired_at"),
        Index(
            "uq_chat_archive_epochs_account_current",
            "account_id",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
        ),
        CheckConstraint("epoch > 0", name="epoch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    epoch: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    encrypted_private_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    account: Mapped["ChatAccount"] = relationship(back_populates="archive_epochs")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
