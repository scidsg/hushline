from flask import current_app

from .crypto import decrypt_field, encrypt_field
from .db import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    primary_username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80))
    _password_hash = db.Column("password_hash", db.String(255))
    _totp_secret = db.Column("totp_secret", db.String(255))
    _email = db.Column("email", db.String(255))
    _smtp_server = db.Column("smtp_server", db.String(255))
    smtp_port = db.Column(db.Integer)
    _smtp_username = db.Column("smtp_username", db.String(255))
    _smtp_password = db.Column("smtp_password", db.String(255))
    _pgp_key = db.Column("pgp_key", db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    # Corrected the relationship and backref here
    secondary_usernames = db.relationship(
        "SecondaryUsername", backref=db.backref("primary_user", lazy=True)
    )

    @property
    def password_hash(self):
        return decrypt_field(self._password_hash)

    @password_hash.setter
    def password_hash(self, value):
        self._password_hash = encrypt_field(value)

    @property
    def totp_secret(self):
        return decrypt_field(self._totp_secret)

    @totp_secret.setter
    def totp_secret(self, value):
        if value is None:
            self._totp_secret = None
        else:
            self._totp_secret = encrypt_field(value)

    @property
    def email(self):
        return decrypt_field(self._email)

    @email.setter
    def email(self, value):
        self._email = encrypt_field(value)

    @property
    def smtp_server(self):
        return decrypt_field(self._smtp_server)

    @smtp_server.setter
    def smtp_server(self, value):
        self._smtp_server = encrypt_field(value)

    @property
    def smtp_username(self):
        return decrypt_field(self._smtp_username)

    @smtp_username.setter
    def smtp_username(self, value):
        self._smtp_username = encrypt_field(value)

    @property
    def smtp_password(self):
        return decrypt_field(self._smtp_password)

    @smtp_password.setter
    def smtp_password(self, value):
        self._smtp_password = encrypt_field(value)

    @property
    def pgp_key(self):
        return decrypt_field(self._pgp_key)

    @pgp_key.setter
    def pgp_key(self, value):
        if value is None:
            self._pgp_key = None
        else:
            self._pgp_key = encrypt_field(value)

    def update_display_name(self, new_display_name):
        """Update the user's display name and remove verification status if the user is verified."""
        self.display_name = new_display_name
        if self.is_verified:
            self.is_verified = False

    # In the User model
    def update_username(self, new_username):
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


class SecondaryUsername(db.Model):
    __tablename__ = "secondary_username"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # This foreign key points to the 'user' table's 'id' field
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    display_name = db.Column(db.String(80), nullable=True)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _content = db.Column("content", db.Text, nullable=False)  # Encrypted content stored here
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("messages", lazy=True))
    secondary_user_id = db.Column(db.Integer, db.ForeignKey("secondary_username.id"), nullable=True)
    secondary_username = db.relationship("SecondaryUsername", backref="messages")

    @property
    def content(self):
        return decrypt_field(self._content)

    @content.setter
    def content(self, value):
        self._content = encrypt_field(value)


class InviteCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255), unique=True, nullable=False)
    expiration_date = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f"<InviteCode {self.code}>"
