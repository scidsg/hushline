import enum
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Set

from flask import current_app
from flask_sqlalchemy.model import Model
from passlib.hash import scrypt
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import Index
from stripe import Event, Invoice

from .crypto import decrypt_field, encrypt_field
from .db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model

from sqlalchemy.orm import Mapped, mapped_column, relationship


class SMTPEncryption(enum.Enum):
    SSL = "SSL"
    StartTLS = "StartTLS"

    @classmethod
    def default(cls) -> "SMTPEncryption":
        return cls.StartTLS


class User(Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_username: Mapped[str] = mapped_column(db.String(80), unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(db.String(80))
    _password_hash: Mapped[str] = mapped_column("password_hash", db.String(512))
    _totp_secret: Mapped[Optional[str]] = mapped_column("totp_secret", db.String(255))
    _email: Mapped[Optional[str]] = mapped_column("email", db.String(255))
    _smtp_server: Mapped[Optional[str]] = mapped_column("smtp_server", db.String(255))
    smtp_port: Mapped[Optional[int]]
    _smtp_username: Mapped[Optional[str]] = mapped_column("smtp_username", db.String(255))
    _smtp_password: Mapped[Optional[str]] = mapped_column("smtp_password", db.String(255))
    _pgp_key: Mapped[Optional[str]] = mapped_column("pgp_key", db.Text)
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_admin: Mapped[bool] = mapped_column(default=False)
    show_in_directory: Mapped[bool] = mapped_column(default=False)
    bio: Mapped[Optional[str]] = mapped_column(db.Text)
    # Corrected the relationship and backref here
    secondary_usernames: Mapped[Set["SecondaryUsername"]] = relationship(
        backref=db.backref("primary_user", lazy=True)
    )
    smtp_encryption: Mapped[SMTPEncryption] = mapped_column(
        db.Enum(SMTPEncryption, native_enum=False), default=SMTPEncryption.StartTLS
    )
    smtp_sender: Mapped[Optional[str]]

    # Extra fields
    extra_field_label1: Mapped[Optional[str]]
    extra_field_value1: Mapped[Optional[str]]
    extra_field_label2: Mapped[Optional[str]]
    extra_field_value2: Mapped[Optional[str]]
    extra_field_label3: Mapped[Optional[str]]
    extra_field_value3: Mapped[Optional[str]]
    extra_field_label4: Mapped[Optional[str]]
    extra_field_value4: Mapped[Optional[str]]
    extra_field_verified1: Mapped[Optional[bool]] = mapped_column(default=False)
    extra_field_verified2: Mapped[Optional[bool]] = mapped_column(default=False)
    extra_field_verified3: Mapped[Optional[bool]] = mapped_column(default=False)
    extra_field_verified4: Mapped[Optional[bool]] = mapped_column(default=False)

    # Paid tier fields
    tier_id: Mapped[int | None] = mapped_column(db.ForeignKey("tiers.id"), nullable=True)
    tier: Mapped["Tier"] = relationship(backref=db.backref("tiers", lazy=True))
    stripe_customer_id = mapped_column(db.String(255))
    stripe_subscription_id = mapped_column(db.String(255))

    @property
    def password_hash(self) -> str:
        """Return the hashed password."""
        return self._password_hash

    @password_hash.setter
    def password_hash(self, plaintext_password: str) -> None:
        """Hash plaintext password using scrypt and store it."""
        self._password_hash = scrypt.hash(plaintext_password)

    def check_password(self, plaintext_password: str) -> bool:
        """Check the plaintext password against the stored hash."""
        return scrypt.verify(plaintext_password, self._password_hash)

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
        return decrypt_field(self._email)

    @email.setter
    def email(self, value: str) -> None:
        self._email = encrypt_field(value)

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
    def pgp_key(self, value: str) -> None:
        if value is None:
            self._pgp_key = None
        else:
            self._pgp_key = encrypt_field(value)

    def update_display_name(self, new_display_name: str) -> None:
        """Update the user's display name and remove verification status if the user is verified."""
        self.display_name = new_display_name
        if self.is_verified:
            self.is_verified = False

    # In the User model
    def update_username(self, new_username: str) -> None:
        """Update the user's username and remove verification status if the user is verified."""
        try:
            # Log the attempt to update the username
            current_app.logger.debug(
                f"Attempting to update username from {self.primary_username} to {new_username}"
            )

            # Update the username
            self.primary_username = new_username
            if self.is_verified:
                self.is_verified = False
                # Log the change in verification status due to username update
                current_app.logger.debug("Verification status set to False due to username update")

            # Commit the change to the database
            db.session.commit()

            # Log the successful update
            current_app.logger.debug(f"Username successfully updated to {new_username}")
        except Exception as e:
            # Log any exceptions that occur during the update
            current_app.logger.error(f"Error updating username: {e}", exc_info=True)

    def __init__(self, primary_username: str) -> None:
        super().__init__()
        self.primary_username = primary_username
        self.tier_id = 1  # Default to the free tier

    __table_args__ = (
        Index(
            "idx_users_stripe_customer_id",
            "stripe_customer_id",
        ),
    )


class AuthenticationLog(Model):
    __tablename__ = "authentication_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship(backref=db.backref("authentication_logs", lazy=True))
    successful: Mapped[bool]
    timestamp: Mapped[datetime] = mapped_column(default=datetime.now)
    otp_code: Mapped[Optional[str]] = mapped_column(db.String(6))
    timecode: Mapped[Optional[int]]

    __table_args__ = (
        Index(
            "idx_authentication_logs_user_id_timestamp_successful",
            "user_id",
            "timestamp",
            "successful",
        ),
    )

    # Open question: should we store the IP address and user agent?
    # It's useful for auditing, but it's identifable
    # ip_address = db.Column(db.String(45), nullable=False)
    # user_agent = db.Column(db.String(255), nullable=False)

    def __init__(
        self,
        user_id: int,
        successful: bool,
        otp_code: str | None = None,
        timecode: int | None = None,
    ) -> None:
        super().__init__()
        self.user_id = user_id
        self.successful = successful
        self.otp_code = otp_code
        self.timecode = timecode


class SecondaryUsername(Model):
    __tablename__ = "secondary_usernames"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True)
    # This foreign key points to the 'user' table's 'id' field
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    display_name: Mapped[Optional[str]] = mapped_column(db.String(80))


class Message(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    _content: Mapped[str] = mapped_column("content", db.Text)  # Encrypted content stored here
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship(backref=db.backref("messages", lazy=True))
    secondary_user_id: Mapped[Optional[int]] = mapped_column(
        db.ForeignKey("secondary_usernames.id")
    )
    secondary_username: Mapped[Set["SecondaryUsername"]] = relationship(
        "SecondaryUsername", backref="messages"
    )

    def __init__(self, content: str, user_id: int) -> None:
        super().__init__()
        self.content = content
        self.user_id = user_id

    @property
    def content(self) -> str | None:
        return decrypt_field(self._content)

    @content.setter
    def content(self, value: str) -> None:
        val = encrypt_field(value)
        if val is not None:
            self._content = val
        else:
            self._content = ""


class InviteCode(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(db.String(255), unique=True)
    expiration_date: Mapped[datetime]

    def __init__(self) -> None:
        super().__init__()
        self.code = secrets.token_urlsafe(16)
        self.expiration_date = datetime.now(timezone.utc) + timedelta(days=365)

    def __repr__(self) -> str:
        return f"<InviteCode {self.code}>"


# Paid tiers
class Tier(Model):
    __tablename__ = "tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), unique=True)
    monthly_amount: Mapped[int] = mapped_column(db.Integer)  # in cents USD
    stripe_product_id = mapped_column(db.String(255), unique=True)
    stripe_price_id = mapped_column(db.String(255), unique=True)

    def __init__(self, name: str, monthly_amount: int) -> None:
        super().__init__()
        self.name = name
        self.monthly_amount = monthly_amount


class StripeEvent(Model):
    __tablename__ = "stripe_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(db.String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(db.String(255))
    event_data: Mapped[str] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    status: Mapped[str] = mapped_column(db.String(255), default="pending")

    def __init__(self, event: Event) -> None:
        super().__init__()
        self.event_id = event.id
        self.event_type = event.type
        self.event_data = str(event)


class StripeInvoiceStatusEnum(enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"


class StripeInvoice(Model):
    __tablename__ = "stripe_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(db.String(255))
    invoice_id: Mapped[str] = mapped_column(db.String(255), unique=True, index=True)
    hosted_invoice_url: Mapped[str] = mapped_column(db.String(255))
    amount_due: Mapped[int] = mapped_column(db.Integer)
    amount_paid: Mapped[int] = mapped_column(db.Integer)
    amount_remaining: Mapped[int] = mapped_column(db.Integer)
    status: Mapped[StripeInvoiceStatusEnum] = mapped_column(
        SQLAlchemyEnum(StripeInvoiceStatusEnum), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    tier_id: Mapped[int] = mapped_column(db.ForeignKey("tiers.id"))

    def __init__(self, invoice: Invoice):
        if invoice.id:
            self.invoice_id = invoice.id
        if invoice.customer and isinstance(invoice.customer, str):
            self.customer_id = invoice.customer
        if invoice.hosted_invoice_url:
            self.hosted_invoice_url = invoice.hosted_invoice_url
        if invoice.amount_due:
            self.amount_due = invoice.amount_due
        else:
            self.amount_due = 0
        if invoice.amount_paid:
            self.amount_paid = invoice.amount_paid
        else:
            self.amount_paid = 0
        if invoice.amount_remaining:
            self.amount_remaining = invoice.amount_remaining
        else:
            self.amount_remaining = 0
        if invoice.status:
            self.status = StripeInvoiceStatusEnum(invoice.status)
        if invoice.created:
            self.created_at = datetime.fromtimestamp(invoice.created, tz=timezone.utc)

        # Look up the user by their customer ID
        user = db.session.query(User).filter_by(stripe_customer_id=invoice.customer).first()
        if user:
            self.user_id = user.id
        else:
            raise ValueError(f"Could not find user with customer ID {invoice.customer}")

        # Look up the tier by the product_id
        if invoice.lines.data[0].plan:
            product_id = invoice.lines.data[0].plan.product

            tier = db.session.query(Tier).filter_by(stripe_product_id=product_id).first()
            if tier:
                self.tier_id = tier.id
            else:
                raise ValueError(f"Could not find tier with product ID {product_id}")
        else:
            raise ValueError("Invoice does not have a plan")
