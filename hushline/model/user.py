import secrets
from typing import TYPE_CHECKING, Any, Optional

from flask import current_app
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.config import AliasMode, FieldsMode
from hushline.crypto import decrypt_field, encrypt_field
from hushline.db import db
from hushline.model.directory_listing_geography import build_directory_geography
from hushline.model.enums import (
    AccountCategory,
    SMTPEncryption,
    StripeSubscriptionStatusEnum,
)
from hushline.model.tier import Tier
from hushline.password_hasher import hash_password, verify_password

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.message import Message
    from hushline.model.notification_recipient import NotificationRecipient
    from hushline.model.username import Username
else:
    Model = db.Model


def _generate_session_id() -> str:
    return secrets.token_urlsafe(48)


class User(Model):
    __tablename__ = "users"

    PASSWORD_MIN_LENGTH = 18
    PASSWORD_MAX_LENGTH = 128
    PASSWORD_HASH_MAX_LENGTH = 512
    TOTP_SECRET_MAX_LENGTH = 255
    EMAIL_MAX_LENGTH = 255
    SMTP_SERVER_MAX_LENGTH = 255
    SMTP_USERNAME_MAX_LENGTH = 255
    SMTP_PASSWORD_MAX_LENGTH = 255
    SMTP_SENDER_MAX_LENGTH = 255
    STRIPE_ID_MAX_LENGTH = 255
    SESSION_ID_MAX_LENGTH = 255
    ACCOUNT_CATEGORY_MAX_LENGTH = 64
    DIRECTORY_LOCATION_MAX_LENGTH = 255

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_cautious: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False, nullable=False
    )
    is_suspended: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False, nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        db.String(SESSION_ID_MAX_LENGTH),
        nullable=False,
        unique=True,
        index=True,
        default=_generate_session_id,
    )
    _password_hash: Mapped[str] = mapped_column(
        "password_hash", db.String(PASSWORD_HASH_MAX_LENGTH)
    )
    _totp_secret: Mapped[Optional[str]] = mapped_column(
        "totp_secret", db.String(TOTP_SECRET_MAX_LENGTH)
    )

    primary_username: Mapped["Username"] = relationship(
        primaryjoin="and_(Username.user_id == User.id, Username.is_primary)",
        back_populates="user",
    )
    notification_recipients: Mapped[list["NotificationRecipient"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="NotificationRecipient.position.asc(), NotificationRecipient.id.asc()",
    )
    messages: Mapped[list["Message"]] = relationship(
        secondary="usernames",
        primaryjoin="Username.user_id == User.id",
        secondaryjoin="Message.username_id == Username.id",
        order_by="Message.id.desc()",
        backref=db.backref("user", lazy=False, uselist=False, viewonly=True),
        lazy=True,
        uselist=True,
        viewonly=True,
    )

    enable_email_notifications: Mapped[bool] = mapped_column(server_default=text("false"))
    email_include_message_content: Mapped[bool] = mapped_column(server_default=text("false"))
    email_encrypt_entire_body: Mapped[bool] = mapped_column(server_default=text("true"))

    _email: Mapped[Optional[str]] = mapped_column("email", db.String(EMAIL_MAX_LENGTH))
    _smtp_server: Mapped[Optional[str]] = mapped_column(
        "smtp_server", db.String(SMTP_SERVER_MAX_LENGTH)
    )
    smtp_port: Mapped[Optional[int]]
    _smtp_username: Mapped[Optional[str]] = mapped_column(
        "smtp_username", db.String(SMTP_USERNAME_MAX_LENGTH)
    )
    _smtp_password: Mapped[Optional[str]] = mapped_column(
        "smtp_password", db.String(SMTP_PASSWORD_MAX_LENGTH)
    )
    _pgp_key: Mapped[Optional[str]] = mapped_column("pgp_key", db.Text)
    smtp_encryption: Mapped[SMTPEncryption] = mapped_column(
        db.Enum(SMTPEncryption, native_enum=False), default=SMTPEncryption.StartTLS
    )
    smtp_sender: Mapped[Optional[str]]

    # Paid tier fields
    tier_id: Mapped[int | None] = mapped_column(db.ForeignKey("tiers.id"), nullable=True)
    tier: Mapped["Tier"] = relationship(backref=db.backref("tiers", lazy=True))

    stripe_customer_id = mapped_column(db.String(STRIPE_ID_MAX_LENGTH), index=True)
    stripe_subscription_id = mapped_column(db.String(STRIPE_ID_MAX_LENGTH), nullable=True)
    stripe_subscription_cancel_at_period_end = mapped_column(db.Boolean, default=False)
    stripe_subscription_status: Mapped[Optional[StripeSubscriptionStatusEnum]] = mapped_column(
        SQLAlchemyEnum(StripeSubscriptionStatusEnum)
    )
    stripe_subscription_current_period_end = mapped_column(
        db.DateTime(timezone=True), nullable=True
    )
    stripe_subscription_current_period_start = mapped_column(
        db.DateTime(timezone=True), nullable=True
    )

    onboarding_complete: Mapped[bool] = mapped_column(server_default=text("false"), default=False)
    account_category: Mapped[Optional[str]] = mapped_column(
        db.String(ACCOUNT_CATEGORY_MAX_LENGTH), nullable=True
    )
    country: Mapped[Optional[str]] = mapped_column(
        db.String(DIRECTORY_LOCATION_MAX_LENGTH), nullable=True
    )
    city: Mapped[Optional[str]] = mapped_column(
        db.String(DIRECTORY_LOCATION_MAX_LENGTH), nullable=True
    )
    subdivision: Mapped[Optional[str]] = mapped_column(
        db.String(DIRECTORY_LOCATION_MAX_LENGTH), nullable=True
    )

    _PREMIUM_ALIAS_COUNT = 100

    @staticmethod
    def new_session_id() -> str:
        return _generate_session_id()

    @property
    def password_hash(self) -> str:
        """Return the hashed password."""
        return self._password_hash

    @password_hash.setter
    def password_hash(self, plaintext_password: str) -> None:
        """Hash plaintext password using scrypt and store it."""
        self._password_hash = hash_password(plaintext_password)

    def check_password(self, plaintext_password: str) -> bool:
        """Check the plaintext password against the stored hash."""
        return verify_password(plaintext_password, self._password_hash)

    @property
    def totp_secret(self) -> str | None:
        return decrypt_field(self._totp_secret)

    @totp_secret.setter
    def totp_secret(self, value: str) -> None:
        if value is None:
            self._totp_secret = None
        else:
            self._totp_secret = encrypt_field(value)

    @property
    def email(self) -> str | None:
        if recipient := self.preferred_notification_recipient:
            return recipient.email
        return decrypt_field(self._email)

    @email.setter
    def email(self, value: str | None) -> None:
        old_email = decrypt_field(self._email)
        self._email = encrypt_field(value) if value is not None else None

        recipient = self.primary_notification_recipient
        if value is not None:
            if recipient is None:
                recipient = self.ensure_primary_notification_recipient()
            if recipient.email in {None, old_email}:
                recipient.email = value
                if recipient.pgp_key is None:
                    recipient.pgp_key = decrypt_field(self._pgp_key)
        elif recipient is not None and recipient.email == old_email:
            recipient.email = None

    @property
    def smtp_server(self) -> str | None:
        return decrypt_field(self._smtp_server)

    @smtp_server.setter
    def smtp_server(self, value: str) -> None:
        self._smtp_server = encrypt_field(value)

    @property
    def smtp_username(self) -> str | None:
        return decrypt_field(self._smtp_username)

    @smtp_username.setter
    def smtp_username(self, value: str) -> None:
        self._smtp_username = encrypt_field(value)

    @property
    def smtp_password(self) -> str | None:
        return decrypt_field(self._smtp_password)

    @smtp_password.setter
    def smtp_password(self, value: str) -> None:
        self._smtp_password = encrypt_field(value)

    @property
    def pgp_key(self) -> str | None:
        return decrypt_field(self._pgp_key)

    @pgp_key.setter
    def pgp_key(self, value: str | None) -> None:
        old_key = decrypt_field(self._pgp_key)
        if value is None:
            self._pgp_key = None
        else:
            self._pgp_key = encrypt_field(value)

        recipient = self.primary_notification_recipient
        if recipient is not None and recipient.pgp_key in {None, old_key}:
            recipient.pgp_key = value

    @property
    def is_free_tier(self) -> bool:
        return self.tier_id is None or self.tier_id == Tier.free_tier_id()

    @property
    def is_business_tier(self) -> bool:
        return self.tier_id == Tier.business_tier_id()

    def set_free_tier(self) -> None:
        self.tier_id = Tier.free_tier_id()

    def set_business_tier(self) -> None:
        self.tier_id = Tier.business_tier_id()

    @property
    def max_aliases(self) -> int:
        alias_mode = current_app.config["ALIAS_MODE"]
        match alias_mode:
            case AliasMode.ALWAYS:
                return 2**32  # just some massive number we'll never have an issue with
            case AliasMode.PREMIUM:
                if self.is_free_tier:
                    return 0
                if not self.is_business_tier:
                    err_msg = f"Programming Error. Unknown tier id: {self.tier_id}"
                    if current_app.config["FLASK_ENV"] == "development":
                        raise Exception(err_msg)
                    current_app.logger.warning(err_msg)
                return self._PREMIUM_ALIAS_COUNT
            case AliasMode.NEVER:
                return 0

        err_msg = f"Programming error. Unhandled alias mode: {alias_mode!r}"
        if current_app.config["FLASK_ENV"] == "development":
            raise Exception(err_msg)
        current_app.logger.warning(err_msg)
        return self._PREMIUM_ALIAS_COUNT

    @property
    def fields_enabled(self) -> bool:
        fields_mode = current_app.config["FIELDS_MODE"]

        if fields_mode == FieldsMode.ALWAYS:
            return True

        return not self.is_free_tier

    @property
    def account_category_label(self) -> str | None:
        if self.account_category is None:
            return None

        legacy_label = AccountCategory.legacy_label(self.account_category)
        if legacy_label is not None:
            return legacy_label

        return AccountCategory.parse_str(self.account_category).label

    @property
    def profile_location(self) -> str | None:
        geography = build_directory_geography(
            city=self.city,
            country=self.country,
            subdivision=self.subdivision,
        )
        if geography.location == "Unknown":
            return None

        if geography.country == "United States":
            parts: list[tuple[str, str]] = []
            if geography.city:
                parts.append((geography.city, geography.city))
            if geography.subdivision:
                parts.append(
                    (geography.subdivision, geography.subdivision_code or geography.subdivision)
                )
            if geography.country:
                parts.append((geography.country, "US"))

            if not parts:
                return None

            leading, *trailing = parts
            rendered_parts = [leading[0], *(abbreviated for _, abbreviated in trailing)]
            return ", ".join(rendered_parts)

        return geography.location

    @property
    def primary_notification_recipient(self) -> "NotificationRecipient | None":
        if not self.notification_recipients:
            return None
        return self.notification_recipients[0]

    @property
    def preferred_notification_recipient(self) -> "NotificationRecipient | None":
        if self.enabled_notification_recipients:
            return self.enabled_notification_recipients[0]
        return self.primary_notification_recipient

    @property
    def enabled_notification_recipients(self) -> list["NotificationRecipient"]:
        return [
            recipient
            for recipient in self.notification_recipients
            if recipient.enabled and recipient.email
        ]

    @property
    def next_notification_recipient_position(self) -> int:
        if not self.notification_recipients:
            return 0
        return max(recipient.position for recipient in self.notification_recipients) + 1

    def ensure_primary_notification_recipient(self) -> "NotificationRecipient":
        from hushline.model.notification_recipient import NotificationRecipient

        recipient = self.primary_notification_recipient
        if recipient is not None:
            return recipient

        recipient = NotificationRecipient(
            enabled=True,
            position=0,
        )
        self.notification_recipients.append(recipient)
        return recipient

    def sync_legacy_notification_email(self) -> None:
        recipient = self.preferred_notification_recipient
        email = recipient.email if recipient is not None else None
        pgp_key = recipient.pgp_key if recipient is not None else None
        self._email = encrypt_field(email) if email is not None else None
        self._pgp_key = encrypt_field(pgp_key) if pgp_key is not None else None

    def __init__(self, **kwargs: Any) -> None:
        for key in ["password_hash", "_password_hash"]:
            if key in kwargs:
                raise ValueError(f"Key {key!r} cannot be mannually set. Try 'password' instead.")
        pw = kwargs.pop("password", None)
        super().__init__(**kwargs)
        self.password_hash = pw
