import secrets
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Generator

from flask import current_app
from flask_sqlalchemy.model import Model
from passlib.hash import argon2
from sqlalchemy.exc import NoResultFound

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
    def value(self, secret: bytes | bytearray) -> None:
        vault = current_app.config.get("VAULT", None)
        if self.name == self._APP_ADMIN_SECRET_SALT_NAME:
            self._value = bytes(secret)
        else:
            self._value = vault.encrypt(bytes(secret), domain=self.name.encode())


class User(Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    _hidden_aad_secret = db.Column("_aad_secret", db.LargeBinary(255), nullable=False)
    primary_username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80))
    _password_revision_number = db.Column(db.Integer, nullable=False)
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
    def _aad_secret(self) -> bytearray:
        domain = b"user_aad_secret"
        aad = deque([self.__tablename__.encode()])
        vault = current_app.config["VAULT"]
        return bytearray(vault.decrypt(self._hidden_aad_secret, domain=domain, aad=aad))

    @_aad_secret.setter
    def _aad_secret(self, value: bytes) -> None:
        domain = b"user_aad_secret"
        aad = deque([self.__tablename__.encode()])
        vault = current_app.config["VAULT"]
        self._hidden_aad_secret = vault.encrypt(value, domain=domain, aad=aad)

    @property
    def password_hash(self) -> str | None:
        """Return the hashed password."""
        return self._password_hash

    @password_hash.setter
    def password_hash(self, plaintext_password: str) -> None:
        """Hash plaintext password using argon2 and store it."""
        domain = b"argon2id_user_password_hash"
        vault = current_app.config["VAULT"]
        self._password_revision_number += 1
        with temp_user_aad(self) as aad:
            aad.extend([byte_order := b"big", encoding := b"utf-8"])
            aad.append(self._password_revision_number.to_bytes(16, byte_order.decode()))
            aad.append(bytearray(plaintext_password, encoding=encoding.decode()))
            # General Warnings & Guidelines:
            # https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
            #
            # This pre-hash isn't vulnerable to password shucking due to the high-entropy and/or
            # user-specific `aad` components, the admin secret, & the other domain separators.
            # Reference:
            # https://www.youtube.com/watch?v=OQD3qDYMyYQ
            #
            # This 32-byte pre-hash is also hex-normalized, which avoids implementation-specific
            # hazards in some password hashing algorithms over raw bytes, & too long passwords.
            # Reference:
            # https://blog.ircmaxell.com/2015/03/security-issue-combining-bcrypt-with.html
            pre_hashed_password = vault._derive_key(domain=domain, aad=aad)
            self._password_hash = argon2.hash(pre_hashed_password.hex())

    def check_password(self, plaintext_password: str) -> bool:
        """Check the plaintext password against the stored hash."""
        domain = b"argon2id_user_password_hash"
        vault = current_app.config["VAULT"]
        with temp_user_aad(self) as aad:
            aad.extend([byte_order := b"big", encoding := b"utf-8"])
            aad.append(self._password_revision_number.to_bytes(16, byte_order.decode()))
            aad.append(bytearray(plaintext_password, encoding=encoding.decode()))
            pre_hashed_password = vault._derive_key(domain=domain, aad=aad)
        return argon2.verify(pre_hashed_password.hex(), self.password_hash)

    @property
    def totp_secret(self) -> str | None:
        domain = b"totp_secret"
        with temp_user_aad(self) as aad:
            return decrypt_field(self._totp_secret, domain=domain, aad=aad)

    @totp_secret.setter
    def totp_secret(self, value: str) -> None:
        domain = b"totp_secret"
        with temp_user_aad(self) as aad:
            self._totp_secret = encrypt_field(value, domain=domain, aad=aad)

    @property
    def email(self) -> str | None:
        domain = b"user_email_address"
        with temp_user_aad(self) as aad:
            return decrypt_field(self._email, domain=domain, aad=aad)

    @email.setter
    def email(self, value: str) -> None:
        domain = b"user_email_address"
        with temp_user_aad(self) as aad:
            self._email = encrypt_field(value, domain=domain, aad=aad)

    @property
    def smtp_server(self) -> str | None:
        domain = b"smtp_server"
        with temp_user_aad(self) as aad:
            return decrypt_field(self._smtp_server, domain=domain, aad=aad)

    @smtp_server.setter
    def smtp_server(self, value: str) -> None:
        domain = b"smtp_server"
        with temp_user_aad(self) as aad:
            self._smtp_server = encrypt_field(value, domain=domain, aad=aad)

    @property
    def smtp_username(self) -> str | None:
        domain = b"smtp_username"
        with temp_user_aad(self) as aad:
            return decrypt_field(self._smtp_username, domain=domain, aad=aad)

    @smtp_username.setter
    def smtp_username(self, value: str) -> None:
        domain = b"smtp_username"
        with temp_user_aad(self) as aad:
            self._smtp_username = encrypt_field(value, domain=domain, aad=aad)

    @property
    def smtp_password(self) -> str | None:
        domain = b"smtp_password"
        with temp_user_aad(self) as aad:
            return decrypt_field(self._smtp_password, domain=domain, aad=aad)

    @smtp_password.setter
    def smtp_password(self, value: str) -> None:
        domain = b"smtp_password"
        with temp_user_aad(self) as aad:
            self._smtp_password = encrypt_field(value, domain=domain, aad=aad)

    @property
    def pgp_key(self) -> str | None:
        domain = b"user_pgp_key"
        with temp_user_aad(self) as aad:
            return decrypt_field(self._pgp_key, domain=domain, aad=aad)

    @pgp_key.setter
    def pgp_key(self, value: str) -> None:
        domain = b"user_pgp_key"
        with temp_user_aad(self) as aad:
            self._pgp_key = encrypt_field(value, domain=domain, aad=aad)

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
        if self.query.filter_by(primary_username=primary_username).first() is None:
            self._password_revision_number = 0
            # hack: outputting bytearray but receiving bytes breaks mypy
            setattr(self, "_aad_secret", secrets.token_bytes(32))


@contextmanager
def temp_user_aad(user: User) -> Generator[deque[bytes | bytearray], None, None]:
    table_name = user.__tablename__.encode()
    user_id = user.id.to_bytes(16, byte_order := "big")
    user_secret = user._aad_secret
    aad = deque([table_name, byte_order.encode(), user_id, user_secret])
    try:
        yield aad
    finally:
        user_secret.clear()
        while aad:
            if isinstance(item := aad.pop(), bytearray):
                item.clear()


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
    _hidden_aad_secret = db.Column("_aad_secret", db.LargeBinary(255), nullable=False)
    _content = db.Column("content", db.Text, nullable=False)  # Encrypted content stored here
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("messages", lazy=True))
    secondary_user_id = db.Column(
        db.Integer, db.ForeignKey("secondary_usernames.id"), nullable=True
    )
    secondary_username = db.relationship("SecondaryUsername", backref="messages")

    def __init__(self, content: str, user_id: int) -> None:
        super().__init__()
        self.user_id = user_id
        # hack: outputting bytearray but receiving bytes breaks mypy
        setattr(self, "_aad_secret", secrets.token_bytes(32))
        self.content = content

    @property
    def _aad_secret(self) -> bytearray:
        domain = b"message_aad_secret"
        user_id = self.user_id.to_bytes(16, byte_order := "big")
        aad = deque([byte_order.encode(), user_id])
        vault = current_app.config["VAULT"]
        return bytearray(vault.decrypt(self._hidden_aad_secret, domain=domain, aad=aad))

    @_aad_secret.setter
    def _aad_secret(self, value: bytes) -> None:
        domain = b"message_aad_secret"
        user_id = self.user_id.to_bytes(16, byte_order := "big")
        aad = deque([byte_order.encode(), user_id])
        vault = current_app.config["VAULT"]
        self._hidden_aad_secret = vault.encrypt(value, domain=domain, aad=aad)

    @property
    def content(self) -> str | None:
        domain = b"user_message_content"
        with temp_message_aad(self) as aad:
            return decrypt_field(self._content, domain=domain, aad=aad)

    @content.setter
    def content(self, value: str) -> None:
        domain = b"user_message_content"
        with temp_message_aad(self) as aad:
            self._content = encrypt_field(value, domain=domain, aad=aad)


@contextmanager
def temp_message_aad(message: Message) -> Generator[deque[bytes | bytearray], None, None]:
    user = User.query.get(message.user_id)
    if user is None:
        raise NoResultFound(f"The user.id: {message.user_id=} was not found.")
    user_id = user.id.to_bytes(16, byte_order := "big")
    user_secret = user._aad_secret
    message_secret = message._aad_secret
    aad = deque([byte_order.encode(), user_id, user_secret, message_secret])
    try:
        yield aad
    finally:
        user_secret.clear()
        message_secret.clear()
        while aad:
            if isinstance(item := aad.pop(), bytearray):
                item.clear()


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
