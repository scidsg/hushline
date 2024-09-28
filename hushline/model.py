import enum
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Generator, Optional, Self, Sequence

from flask_sqlalchemy.model import Model
from passlib.hash import scrypt
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .crypto import decrypt_field, encrypt_field
from .db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


@enum.unique
class SMTPEncryption(enum.Enum):
    SSL = "SSL"
    StartTLS = "StartTLS"

    @classmethod
    def default(cls) -> "SMTPEncryption":
        return cls.StartTLS


class HostOrganization(Model):
    __tablename__ = "host_organization"

    _DEFAULT_ID: int = 1
    _DEFAULT_BRAND_PRIMARY_HEX_COLOR: str = "#7d25c1"
    _DEFAULT_BRAND_APP_NAME: str = "🤫 Hush Line"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_app_name: Mapped[str] = mapped_column(db.String(255), default=_DEFAULT_BRAND_APP_NAME)
    brand_primary_hex_color: Mapped[str] = mapped_column(
        db.String(7), default=_DEFAULT_BRAND_PRIMARY_HEX_COLOR
    )

    @classmethod
    def fetch(cls) -> Self | None:
        return db.session.get(cls, cls._DEFAULT_ID)

    @classmethod
    def fetch_or_default(cls) -> Self:
        return cls.fetch() or cls()

    def __init__(self, id: int | None = None) -> None:
        super().__init__()
        self.id = id if id is not None else self._DEFAULT_ID


@dataclass(frozen=True, repr=False, eq=False)
class ExtraField:
    label: Optional[str]
    value: Optional[str]
    is_verified: Optional[bool]


class Username(Model):
    """
    Class representing a username and associated profile.
    This was pulled out of the `User` class so that a `username` could be globally unique among
    both users and aliases and enforced at the database level.
    """

    __tablename__ = "usernames"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship()
    _username: Mapped[str] = mapped_column("username", unique=True)
    _display_name: Mapped[Optional[str]] = mapped_column("display_name", db.String(80))
    is_primary: Mapped[bool] = mapped_column()
    is_verified: Mapped[bool] = mapped_column(default=False)
    show_in_directory: Mapped[bool] = mapped_column(default=False)
    bio: Mapped[Optional[str]] = mapped_column(db.Text)

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

    def __init__(
        self,
        _username: str,
        is_primary: bool,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._username = _username
        self.is_primary = is_primary

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        self._username = username
        self.is_verified = False

    @property
    def display_name(self) -> Optional[str]:
        return self._display_name

    @display_name.setter
    def display_name(self, display_name: str | None) -> None:
        self._display_name = display_name
        self.is_verified = False

    @property
    def extra_fields(self) -> Generator[ExtraField, None, None]:
        for i in range(1, 5):
            yield ExtraField(
                getattr(self, f"extra_field_label{i}", None),
                getattr(self, f"extra_field_value{i}", None),
                getattr(self, f"extra_field_verified{i}", None),
            )

    @property
    def valid_fields(self) -> Sequence[ExtraField]:
        return [x for x in self.extra_fields if x.label and x.value]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} username={self.username}>"


class User(Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    _password_hash: Mapped[str] = mapped_column("password_hash", db.String(512))
    _totp_secret: Mapped[Optional[str]] = mapped_column("totp_secret", db.String(255))

    primary_username: Mapped[Username] = relationship(
        primaryjoin="and_(Username.user_id == User.id, Username.is_primary)",
        back_populates="user",
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

    _email: Mapped[Optional[str]] = mapped_column("email", db.String(255))
    _smtp_server: Mapped[Optional[str]] = mapped_column("smtp_server", db.String(255))
    smtp_port: Mapped[Optional[int]]
    _smtp_username: Mapped[Optional[str]] = mapped_column("smtp_username", db.String(255))
    _smtp_password: Mapped[Optional[str]] = mapped_column("smtp_password", db.String(255))
    _pgp_key: Mapped[Optional[str]] = mapped_column("pgp_key", db.Text)
    smtp_encryption: Mapped[SMTPEncryption] = mapped_column(
        db.Enum(SMTPEncryption, native_enum=False), default=SMTPEncryption.StartTLS
    )
    smtp_sender: Mapped[Optional[str]]

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

    def __init__(self, **kwargs: Any) -> None:
        for key in ["password_hash", "_password_hash"]:
            if key in kwargs:
                raise ValueError(f"Key {key!r} cannot be mannually set. Try 'password' instead.")
        pw = kwargs.pop("password", None)
        super().__init__()
        self.password_hash = pw


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


class Message(Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    _content: Mapped[str] = mapped_column("content", db.Text)  # Encrypted content stored here
    username_id: Mapped[int] = mapped_column(db.ForeignKey("usernames.id"))
    username: Mapped["Username"] = relationship(uselist=False)

    def __init__(self, content: str, **kwargs: Any) -> None:
        if "_content" in kwargs:
            raise ValueError("Cannot set '_content' directly. Use 'content'")
        super().__init__(**kwargs)
        self.content = content

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
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(db.String(255), unique=True)
    expiration_date: Mapped[datetime]

    def __init__(self) -> None:
        super().__init__()
        self.code = secrets.token_urlsafe(16)
        self.expiration_date = datetime.now(timezone.utc) + timedelta(days=365)

    def __repr__(self) -> str:
        return f"<InviteCode {self.code}>"
