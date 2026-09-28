import secrets
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


class WebAuthnUserHandle(Model):
    __tablename__ = "webauthn_user_handles"
    __table_args__ = (
        CheckConstraint(
            "octet_length(handle) = 64",
            name="ck_webauthn_user_handles_handle_length",
        ),
    )

    HANDLE_LENGTH = 64

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    handle: Mapped[bytes] = mapped_column(
        db.LargeBinary(HANDLE_LENGTH), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="webauthn_user_handle")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("handle", secrets.token_bytes(self.HANDLE_LENGTH))
        super().__init__(**kwargs)


class WebAuthnCredential(Model):
    __tablename__ = "webauthn_credentials"
    __table_args__ = (
        CheckConstraint("sign_count >= 0", name="ck_webauthn_credentials_sign_count"),
        CheckConstraint(
            "algorithm IN (-8, -7, -257)",
            name="ck_webauthn_credentials_algorithm",
        ),
        CheckConstraint(
            "octet_length(credential_id) BETWEEN 1 AND 1024",
            name="ck_webauthn_credentials_id_length",
        ),
        CheckConstraint(
            "octet_length(public_key) BETWEEN 1 AND 4096",
            name="ck_webauthn_credentials_public_key_length",
        ),
        Index("ix_webauthn_credentials_user_active", "user_id", "disabled_at"),
    )

    MAX_CREDENTIAL_ID_LENGTH = 1024
    MAX_PUBLIC_KEY_LENGTH = 4096
    MAX_NAME_LENGTH = 100

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[bytes] = mapped_column(
        db.LargeBinary(MAX_CREDENTIAL_ID_LENGTH), nullable=False, unique=True, index=True
    )
    public_key: Mapped[bytes] = mapped_column(db.LargeBinary(MAX_PUBLIC_KEY_LENGTH), nullable=False)
    algorithm: Mapped[int] = mapped_column(nullable=False)
    sign_count: Mapped[int] = mapped_column(db.BigInteger, default=0, nullable=False)
    transports: Mapped[list[str]] = mapped_column(db.JSON, default=list, nullable=False)
    device_type: Mapped[str] = mapped_column(db.String(32), nullable=False)
    backed_up: Mapped[bool] = mapped_column(default=False, nullable=False)
    name: Mapped[str | None] = mapped_column(db.String(MAX_NAME_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="webauthn_credentials")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class WebAuthnChallenge(Model):
    __tablename__ = "webauthn_challenges"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('registration', 'authentication', 'recovery')",
            name="ck_webauthn_challenges_purpose",
        ),
        CheckConstraint(
            "octet_length(challenge_hash) = 32",
            name="ck_webauthn_challenges_challenge_hash_length",
        ),
        CheckConstraint(
            "octet_length(session_binding_hash) = 32",
            name="ck_webauthn_challenges_session_hash_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_webauthn_challenges_expiry",
        ),
        Index(
            "ix_webauthn_challenges_account_purpose_created",
            "user_id",
            "purpose",
            "created_at",
        ),
        Index(
            "ix_webauthn_challenges_session_purpose_created",
            "session_binding_hash",
            "purpose",
            "created_at",
        ),
    )

    DIGEST_LENGTH = 32
    PURPOSE_MAX_LENGTH = 32

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(db.String(PURPOSE_MAX_LENGTH), nullable=False)
    challenge_hash: Mapped[bytes] = mapped_column(
        db.LargeBinary(DIGEST_LENGTH), nullable=False, unique=True, index=True
    )
    session_binding_hash: Mapped[bytes] = mapped_column(
        db.LargeBinary(DIGEST_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="webauthn_challenges")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)
