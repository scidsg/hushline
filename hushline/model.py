import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from flask import current_app
from flask_sqlalchemy.model import Model
from passlib.hash import scrypt

from .crypto import decrypt_field, encrypt_field
from .db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class InfrastructureAdmin(Model):
    __tablename__ = "infrastructure_admin"

    _APP_ADMIN_SECRET_SALT_NAME: str = "app_admin_secret_salt"
    _FLASK_COOKIE_SECRET_KEY_NAME: str = "flask_cookie_secret_key"

    name = db.Column(db.String(255), primary_key=True)
    _value = db.Column(db.LargeBinary(255), nullable=False)

    def __init__(self, name: str, value: bytes | bytearray) -> None:
        super().__init__()
        self.name = name
        # hack: outputting bytearray but receiving bytes breaks mypy
        setattr(self, "value", value)

    @property
    def value(self) -> bytearray:
        vault = current_app.config.get("VAULT", None)
        if self.name == self._APP_ADMIN_SECRET_SALT_NAME:
            return bytearray(self._value)
        return bytearray(vault.decrypt(self._value, domain=self.name.encode()))

    @value.setter
    def value(self, secret: bytes) -> None:
        vault = current_app.config.get("VAULT", None)
        if self.name == self._APP_ADMIN_SECRET_SALT_NAME:
            self._value = bytes(secret)
        else:
            self._value = vault.encrypt(bytes(secret), domain=self.name.encode())


class User(Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    primary_username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80))
    _password_hash = db.Column("password_hash", db.String(512))
    _totp_secret = db.Column("totp_secret", db.String(255))
    _email = db.Column("email", db.String(255))
    _smtp_server = db.Column("smtp_server", db.String(255))
    smtp_port = db.Column(db.Integer)
    _smtp_username = db.Column("smtp_username", db.String(255))
    _smtp_password = db.Column("smtp_password", db.String(255))
    _pgp_key = db.Column("pgp_key", db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    show_in_directory = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text, nullable=True)
    # Corrected the relationship and backref here
    secondary_usernames = db.relationship(
        "SecondaryUsername", backref=db.backref("primary_user", lazy=True)
    )

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
        return decrypt_field(self._totp_secret, domain=b"totp_secret")

    @totp_secret.setter
    def totp_secret(self, value: str) -> None:
        if value is None:
            self._totp_secret = None
        else:
            self._totp_secret = encrypt_field(value, domain=b"totp_secret")

    @property
    def email(self) -> str | None:
        return decrypt_field(self._email, domain=b"user_email_address")

    @email.setter
    def email(self, value: str) -> None:
        self._email = encrypt_field(value, domain=b"user_email_address")

    @property
    def smtp_server(self) -> str | None:
        return decrypt_field(self._smtp_server, domain=b"smtp_server")

    @smtp_server.setter
    def smtp_server(self, value: str) -> None:
        self._smtp_server = encrypt_field(value, domain=b"smtp_server")

    @property
    def smtp_username(self) -> str | None:
        return decrypt_field(self._smtp_username, domain=b"smtp_username")

    @smtp_username.setter
    def smtp_username(self, value: str) -> None:
        self._smtp_username = encrypt_field(value, domain=b"smtp_username")

    @property
    def smtp_password(self) -> str | None:
        return decrypt_field(self._smtp_password, domain=b"smtp_password")

    @smtp_password.setter
    def smtp_password(self, value: str) -> None:
        self._smtp_password = encrypt_field(value, domain=b"smtp_password")

    @property
    def pgp_key(self) -> str | None:
        return decrypt_field(self._pgp_key, domain=b"user_pgp_key")

    @pgp_key.setter
    def pgp_key(self, value: str) -> None:
        if value is None:
            self._pgp_key = None
        else:
            self._pgp_key = encrypt_field(value, domain=b"user_pgp_key")

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


class AuthenticationLog(Model):
    __tablename__ = "authentication_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("authentication_logs", lazy=True))
    successful = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    otp_code = db.Column(db.String(6), nullable=True)
    timecode = db.Column(db.Integer, nullable=True)

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

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # This foreign key points to the 'user' table's 'id' field
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    display_name = db.Column(db.String(80), nullable=True)


class Message(Model):
    id = db.Column(db.Integer, primary_key=True)
    _content = db.Column("content", db.Text, nullable=False)  # Encrypted content stored here
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("messages", lazy=True))
    secondary_user_id = db.Column(
        db.Integer, db.ForeignKey("secondary_usernames.id"), nullable=True
    )
    secondary_username = db.relationship("SecondaryUsername", backref="messages")

    def __init__(self, content: str, user_id: int) -> None:
        super().__init__()
        self.content = content
        self.user_id = user_id

    @property
    def content(self) -> str | None:
        return decrypt_field(self._content, domain=b"message_content")

    @content.setter
    def content(self, value: str) -> None:
        self._content = encrypt_field(value, domain=b"message_content")


class InviteCode(Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255), unique=True, nullable=False)
    expiration_date = db.Column(db.DateTime, nullable=False)

    def __init__(self) -> None:
        super().__init__()
        self.code = secrets.token_urlsafe(16)
        self.expiration_date = datetime.now(timezone.utc) + timedelta(days=365)

    def __repr__(self) -> str:
        return f"<InviteCode {self.code}>"
