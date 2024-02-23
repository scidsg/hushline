from hushline.flask_app.db import db  # Adjust the import path if necessary
from hushline.crypto import encrypt_field, decrypt_field  # Adjust the import path if necessary

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    primary_username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80))
    _password_hash = db.Column('password_hash', db.String(255))
    _totp_secret = db.Column('totp_secret', db.String(255), nullable=True)
    _email = db.Column('email', db.String(255))
    _smtp_server = db.Column('smtp_server', db.String(255))
    smtp_port = db.Column(db.Integer)
    _smtp_username = db.Column('smtp_username', db.String(255))
    _smtp_password = db.Column('smtp_password', db.String(255))
    _pgp_key = db.Column('pgp_key', db.Text, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    has_paid = db.Column(db.Boolean, default=False)
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)
    paid_features_expiry = db.Column(db.DateTime, nullable=True)
    is_subscription_active = db.Column(db.Boolean, default=True)
    secondary_users = db.relationship('SecondaryUser', backref='primary_user', lazy=True)

    @property
    def password(self):
        raise AttributeError('Password is not a readable attribute.')

    @password.setter
    def password(self, password):
        self._password_hash = encrypt_field(password)

    def verify_password(self, plaintext_password):
        return self._password_hash == encrypt_field(plaintext_password)

    # Additional properties for encrypted fields as needed

class SecondaryUser(db.Model):
    __tablename__ = 'secondary_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    display_name = db.Column(db.String(80), nullable=True)

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    _content = db.Column('content', db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    secondary_user_id = db.Column(db.Integer, db.ForeignKey('secondary_user.id'), nullable=True)

    @property
    def content(self):
        return decrypt_field(self._content)

    @content.setter
    def content(self, value):
        self._content = encrypt_field(value)

class InviteCode(db.Model):
    __tablename__ = 'invite_code'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255), unique=True, nullable=False)
    expiration_date = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f'<InviteCode {self.code}>'
