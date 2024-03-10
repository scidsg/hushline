# Standard Library Imports
import os
import io
import base64
import logging
import re
import stripe
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse, urljoin

# Flask Framework and Extensions
from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    session,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from flask_migrate import Migrate
from flask_limiter import Limiter, RateLimitExceeded
from flask_limiter.util import get_remote_address
from redis.exceptions import ConnectionError as RedisConnectionError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash, safe_join

# Form Handling and Validation
from wtforms import TextAreaField, StringField, PasswordField, IntegerField
from wtforms.validators import DataRequired, Length, Email, ValidationError

# Cryptography and Security
import pyotp
import gnupg
from cryptography.fernet import Fernet

# Database and Error Handling
from sqlalchemy.exc import IntegrityError  # Import IntegrityError
from sqlalchemy.engine import create_engine

# Environment Variables
from dotenv import load_dotenv

# QR Code Generation
import qrcode

# Utility Decorators
from functools import wraps


# Load environment variables
load_dotenv()

# Retrieve database credentials and secret key from environment
db_user = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASS")
db_name = os.getenv("DB_NAME")
secret_key = os.getenv("SECRET_KEY")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
stripe_webhook_secret = os.getenv("STRIPE_WH_SECRET")

# Load registration codes requirement setting from environment variable
require_invite_code = os.getenv("REGISTRATION_CODES_REQUIRED", "True") == "True"

app = Flask(__name__)

# Init Flask Limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://localhost:6379",
)


# Handle Rate Limit Exceeded Error
@app.errorhandler(RateLimitExceeded)
def handle_rate_limit_exceeded(e):
    return render_template("rate_limit_exceeded.html"), 429


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

app.config["SECRET_KEY"] = secret_key

ssl_cert = "/etc/mariadb/ssl/fullchain.pem"
ssl_key = "/etc/mariadb/ssl/privkey.pem"

# Ensure SSL files exist
if not all(os.path.exists(path) for path in [ssl_cert, ssl_key]):
    raise FileNotFoundError("SSL certificate or key file is missing.")

# SQLAlchemy database URI with SSL configuration
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{db_user}:{db_pass}@localhost/{db_name}"
    "?ssl_cert={ssl_cert}&ssl_key={ssl_key}".format(ssl_cert=ssl_cert, ssl_key=ssl_key)
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Session configuration for secure cookies
app.config["SESSION_COOKIE_NAME"] = "__Host-session"
app.config["SESSION_COOKIE_SECURE"] = True  # Only send cookies over HTTPS
app.config[
    "SESSION_COOKIE_HTTPONLY"
] = True  # Prevent JavaScript access to session cookie
app.config[
    "SESSION_COOKIE_SAMESITE"
] = "Lax"  # Control cookie sending with cross-site requests
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

# Initialize GPG with expanded home directory
gpg_home = os.path.expanduser("~/.gnupg")
gpg = gnupg.GPG(gnupghome=gpg_home)

# Initialize extensions
bcrypt = Bcrypt(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Setup file handler
file_handler = RotatingFileHandler(
    "flask.log", maxBytes=1024 * 1024 * 100, backupCount=20
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    )
)


# Add it to the Flask logger
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.DEBUG)


############################################################################################################
############################################################################################################

# ENCRYPTION
# Hush Line uses encryption at rest to protect user data.

############################################################################################################
############################################################################################################


# Load encryption key
encryption_key = os.getenv("ENCRYPTION_KEY")
if encryption_key is None:
    raise ValueError("Encryption key not found. Please check your .env file.")
fernet = Fernet(encryption_key)


def encrypt_field(data):
    if data is None:
        return None
    return fernet.encrypt(data.encode()).decode()


def decrypt_field(data):
    if data is None:
        return None
    return fernet.decrypt(data.encode()).decode()


############################################################################################################
############################################################################################################

# MODELS
# Database models for users, secondary usernames, messages, and invite codes.

############################################################################################################
############################################################################################################


# Database Models
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
    has_paid = db.Column(db.Boolean, default=False)
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)
    paid_features_expiry = db.Column(db.DateTime, nullable=True)
    is_subscription_active = db.Column(db.Boolean, default=False)
    # Corrected the relationship and backref here
    secondary_users = db.relationship(
        "SecondaryUser", backref=db.backref("primary_user", lazy=True)
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
            app.logger.debug(
                f"Attempting to update username from {self.primary_username} to {new_username}"
            )

            # Update the username
            self.primary_username = new_username
            if self.is_verified:
                self.is_verified = False
                # Log the change in verification status due to username update
                app.logger.debug(
                    f"Verification status set to False due to username update"
                )

            # Commit the change to the database
            db.session.commit()

            # Log the successful update
            app.logger.debug(f"Username successfully updated to {new_username}")
        except Exception as e:
            # Log any exceptions that occur during the update
            app.logger.error(f"Error updating username: {e}", exc_info=True)


class SecondaryUser(db.Model):
    __tablename__ = "secondary_user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # This foreign key points to the 'user' table's 'id' field
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    display_name = db.Column(db.String(80), nullable=True)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _content = db.Column(
        "content", db.Text, nullable=False
    )  # Encrypted content stored here
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Add a foreign key to reference secondary usernames
    secondary_user_id = db.Column(
        db.Integer, db.ForeignKey("secondary_user.id"), nullable=True
    )

    # Relationship with User model
    user = db.relationship("User", backref=db.backref("messages", lazy=True))

    # New relationship to link a message to a specific secondary username (if applicable)
    secondary_user = db.relationship("SecondaryUser", backref="messages")

    @property
    def content(self):
        """Decrypt and return the message content."""
        return decrypt_field(self._content)

    @content.setter
    def content(self, value):
        """Encrypt and store the message content."""
        self._content = encrypt_field(value)


class InviteCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255), unique=True, nullable=False)
    expiration_date = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f"<InviteCode {self.code}>"


############################################################################################################
############################################################################################################

# FORMS

############################################################################################################
############################################################################################################


# Password Policy
class ComplexPassword(object):
    def __init__(self, message=None):
        if not message:
            message = "⛔️ Password must include uppercase, lowercase, digit, and a special character."
        self.message = message

    def __call__(self, form, field):
        password = field.data
        if not (
            re.search("[A-Z]", password)
            and re.search("[a-z]", password)
            and re.search("[0-9]", password)
            and re.search("[^A-Za-z0-9]", password)
        ):
            raise ValidationError(self.message)


class MessageForm(FlaskForm):
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=2000)],
        render_kw={"placeholder": "Include a contact method if you want a response..."},
    )


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class TwoFactorForm(FlaskForm):
    verification_code = StringField(
        "2FA Code", validators=[DataRequired(), Length(min=6, max=6)]
    )


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=25)]
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )
    invite_code = StringField(
        "Invite Code", validators=[DataRequired(), Length(min=6, max=25)]
    )


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("Old Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )


class ChangeUsernameForm(FlaskForm):
    new_username = StringField(
        "New Username", validators=[DataRequired(), Length(min=4, max=25)]
    )


class SMTPSettingsForm(FlaskForm):
    smtp_server = StringField("SMTP Server", validators=[DataRequired()])
    smtp_port = IntegerField("SMTP Port", validators=[DataRequired()])
    smtp_username = StringField("SMTP Username", validators=[DataRequired()])
    smtp_password = PasswordField("SMTP Password", validators=[DataRequired()])


class PGPKeyForm(FlaskForm):
    pgp_key = TextAreaField("PGP Key", validators=[Length(max=20000)])


class DisplayNameForm(FlaskForm):
    display_name = StringField("Display Name", validators=[Length(max=100)])


@app.errorhandler(404)
def page_not_found(e):
    flash("⛓️‍💥 That page doesn't exist.", "warning")
    return redirect(url_for("index"))


def require_2fa(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or not session.get("is_authenticated", False):
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))
        if session.get("2fa_required", False) and not session.get(
            "2fa_verified", False
        ):
            flash("👉 2FA verification required.")
            return redirect(url_for("verify_2fa_login"))
        return f(*args, **kwargs)

    return decorated_function


@app.context_processor
def inject_user():
    if "user_id" in session:
        user = User.query.get(session["user_id"])
        return {"user": user}
    return {}


# Error Handler
@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error and stacktrace
    app.logger.error(f"Error: {e}", exc_info=True)
    return "An internal server error occurred", 500


############################################################################################################
############################################################################################################

# ROUTES
# All views of the app. Settings in the next section.

############################################################################################################
############################################################################################################


@app.route("/")
@limiter.limit("120 per minute")
def index():
    if "user_id" in session:
        user = User.query.get(session["user_id"])
        if user:
            return redirect(url_for("inbox", username=user.primary_username))
        else:
            # Handle case where user ID in session does not exist in the database
            flash("🫥 User not found. Please log in again.")
            session.pop("user_id", None)  # Clear the invalid user_id from session
            return redirect(url_for("login"))
    else:
        return redirect(url_for("login"))


@app.route("/inbox")
@limiter.limit("120 per minute")
@require_2fa
def inbox():
    # Redirect if not logged in
    if "user_id" not in session:
        flash("Please log in to access your inbox.")
        return redirect(url_for("login"))

    logged_in_user_id = session["user_id"]

    # Check for a 'username' query parameter and compare it with the logged-in user's username
    requested_username = request.args.get("username")
    logged_in_username = User.query.get(logged_in_user_id).primary_username

    # If the requested username does not match the logged-in user's username, redirect to the correct inbox URL
    if requested_username and requested_username != logged_in_username:
        return redirect(
            url_for("inbox")
        )  # Removes any 'username' query parameter to avoid confusion

    # Proceed with loading the inbox as before
    primary_user = User.query.get(logged_in_user_id)
    messages = (
        Message.query.filter_by(user_id=primary_user.id)
        .order_by(Message.id.desc())
        .all()
    )
    secondary_users_dict = {su.id: su for su in primary_user.secondary_users}

    return render_template(
        "inbox.html",
        user=primary_user,
        secondary_user=None,
        messages=messages,
        is_secondary=False,
        secondary_users=secondary_users_dict,
    )


def get_email_from_pgp_key(pgp_key):
    try:
        # Import the PGP key
        imported_key = gpg.import_keys(pgp_key)

        if imported_key.count > 0:
            # Get the Key ID of the imported key
            key_id = imported_key.results[0]["fingerprint"][-16:]

            # List all keys to find the matching key
            all_keys = gpg.list_keys()
            for key in all_keys:
                if key["keyid"] == key_id:
                    # Extract email from the uid (user ID)
                    uids = key["uids"][0]
                    email_start = uids.find("<") + 1
                    email_end = uids.find(">")
                    if email_start > 0 and email_end > email_start:
                        return uids[email_start:email_end]
    except Exception as e:
        app.logger.error(f"Error extracting email from PGP key: {e}")

    return None


@app.route("/submit_message/<username>", methods=["GET", "POST"])
@limiter.limit("120 per minute")
def submit_message(username):
    form = MessageForm()

    user = None
    secondary_user = None
    display_name_or_username = ""

    primary_user = User.query.filter_by(primary_username=username).first()
    if primary_user:
        user = primary_user
        display_name_or_username = (
            primary_user.display_name or primary_user.primary_username
        )
    else:
        secondary_user = SecondaryUser.query.filter_by(username=username).first()
        if secondary_user:
            user = secondary_user.primary_user
            display_name_or_username = (
                secondary_user.display_name or secondary_user.username
            )
            # Check if the subscription has expired
            if not user.has_paid or (
                user.paid_features_expiry
                and user.paid_features_expiry < datetime.utcnow()
            ):
                flash(
                    "⚠️ This feature requires a premium account. Please upgrade to access.",
                    "warning",
                )
                return redirect(url_for("settings"))

    if not user:
        flash("🫥 User not found.")
        return redirect(url_for("index"))

    if form.validate_on_submit():
        content = form.content.data
        client_side_encrypted = (
            request.form.get("client_side_encrypted", "false") == "true"
        )

        if not client_side_encrypted and user.pgp_key:
            # Get the email address from the PGP key
            pgp_email = get_email_from_pgp_key(user.pgp_key)
            if pgp_email:
                # Append the note indicating server-side encryption
                content_with_note = content
                # Now call encrypt_message with the correct pgp_email
                encrypted_content = encrypt_message(content_with_note, pgp_email)
                email_content = encrypted_content if encrypted_content else content
                if not encrypted_content:
                    flash("⛔️ Failed to encrypt message with PGP key.", "error")
                    return redirect(url_for("submit_message", username=username))
            else:
                flash("⛔️ Unable to extract email from PGP key.", "error")
                return redirect(url_for("submit_message", username=username))
        else:
            email_content = content if client_side_encrypted else content

        # Your logic to save and possibly email the message...
        new_message = Message(
            content=email_content,
            user_id=user.id,
            secondary_user_id=secondary_user.id if secondary_user else None,
        )
        db.session.add(new_message)
        db.session.commit()

        if all(
            [
                user.email,
                user.smtp_server,
                user.smtp_port,
                user.smtp_username,
                user.smtp_password,
            ]
        ):
            try:
                sender_email = user.smtp_username
                # Assume send_email is a utility function to send emails
                email_sent = send_email(
                    user.email, "New Message", email_content, user, sender_email
                )
                flash_message = (
                    "👍 Message submitted and email sent successfully."
                    if email_sent
                    else "👍 Message submitted, but failed to send email."
                )
                flash(flash_message)
            except Exception as e:
                flash(
                    "👍 Message submitted, but an error occurred while sending email.",
                    "warning",
                )
        else:
            flash("👍 Message submitted successfully.")

        return redirect(url_for("submit_message", username=username))

    return render_template(
        "submit_message.html",
        form=form,
        user=user,
        secondary_user=secondary_user if secondary_user else None,
        username=username,
        display_name_or_username=display_name_or_username,
        current_user_id=session.get("user_id"),
        public_key=user.pgp_key,
    )


def send_email(recipient, subject, body, user, sender_email):
    app.logger.debug(
        f"SMTP settings being used: Server: {user.smtp_server}, Port: {user.smtp_port}, Username: {user.smtp_username}"
    )
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = sender_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(
            user.smtp_server, user.smtp_port, timeout=10
        ) as server:  # Added timeout
            server.starttls()
            server.login(user.smtp_username, user.smtp_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        app.logger.info("Email sent successfully.")
        return True
    except Exception as e:
        app.logger.error(f"Error sending email: {e}", exc_info=True)
        return False


def is_valid_pgp_key(key):
    app.logger.debug(f"Attempting to import key: {key}")
    try:
        imported_key = gpg.import_keys(key)
        app.logger.info(f"Key import attempt: {imported_key.results}")
        return imported_key.count > 0
    except Exception as e:
        app.logger.error(f"Error importing PGP key: {e}")
        return False


def encrypt_message(message, recipient_email):
    gpg = gnupg.GPG(gnupghome=gpg_home, options=["--trust-model", "always"])
    app.logger.info(f"Encrypting message for recipient: {recipient_email}")

    try:
        # Ensure the message is a byte string encoded in UTF-8
        if isinstance(message, str):
            message = message.encode("utf-8")
        encrypted_data = gpg.encrypt(
            message, recipients=recipient_email, always_trust=True
        )

        if not encrypted_data.ok:
            app.logger.error(f"Encryption failed: {encrypted_data.status}")
            return None

        return str(encrypted_data)
    except Exception as e:
        app.logger.error(f"Error during encryption: {e}")
        return None


def list_keys():
    try:
        public_keys = gpg.list_keys()
        app.logger.info("Public keys in the keyring:")
        for key in public_keys:
            app.logger.info(f"Key: {key}")
    except Exception as e:
        app.logger.error(f"Error listing keys: {e}")


# Call this function after key import or during troubleshooting
list_keys()


@app.route("/delete_message/<int:message_id>", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def delete_message(message_id):
    if "user_id" not in session:
        flash("🔑 Please log in to continue.")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user:
        flash("🫥 User not found. Please log in again.")
        return redirect(url_for("login"))

    message = Message.query.get(message_id)
    if message and message.user_id == user.id:
        db.session.delete(message)
        db.session.commit()
        flash("🗑️ Message deleted successfully.")
    else:
        flash("⛔️ Message not found or unauthorized access.")

    return redirect(url_for("inbox", username=user.primary_username))


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("120 per minute")
def register():
    form = RegistrationForm()
    # Dynamically adjust form field based on invite code requirement
    if not require_invite_code:
        del form.invite_code  # Remove invite_code field if not required

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        # Only process invite code if required
        invite_code_input = form.invite_code.data if require_invite_code else None

        if require_invite_code:
            # Validate the invite code
            invite_code = InviteCode.query.filter_by(code=invite_code_input).first()
            if not invite_code or invite_code.expiration_date < datetime.utcnow():
                flash("⛔️ Invalid or expired invite code.", "error")
                return redirect(url_for("register"))

        # Check for existing username (assuming primary_username is the field to check against)
        if User.query.filter_by(primary_username=username).first():
            flash("💔 Username already taken.", "error")
            return redirect(url_for("register"))

        # Hash the password and create the user
        password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        new_user = User(primary_username=username, password_hash=password_hash)

        # Add user to the database
        db.session.add(new_user)
        db.session.commit()

        flash("👍 Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    # Pass the flag to template to conditionally render invite code field
    return render_template(
        "register.html", form=form, require_invite_code=require_invite_code
    )


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("120 per minute")
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data  # This is input from the form
        password = form.password.data

        # Use primary_username for filter_by
        user = User.query.filter_by(primary_username=username).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            session.permanent = (
                True  # Make the session permanent so it uses the configured lifetime
            )
            session["user_id"] = user.id
            session[
                "username"
            ] = user.primary_username  # Store primary_username in session
            session["is_authenticated"] = True  # Mark user as authenticated
            session["2fa_required"] = (
                user.totp_secret is not None
            )  # Check if 2FA is required
            session["2fa_verified"] = False  # Initially mark 2FA as not verified
            session["is_admin"] = user.is_admin  # Store admin status in session

            if user.totp_secret:
                # If 2FA is enabled, redirect to the 2FA verification page
                return redirect(url_for("verify_2fa_login"))
            else:
                # If 2FA is not enabled, directly log the user in
                session[
                    "2fa_verified"
                ] = True  # Mark 2FA as verified since it's not required
                return redirect(url_for("inbox", username=user.primary_username))
        else:
            flash("⛔️ Invalid username or password")

    return render_template("login.html", form=form)


@app.route("/verify-2fa-login", methods=["GET", "POST"])
@limiter.limit("120 per minute")
def verify_2fa_login():
    # Redirect to login if user is not authenticated
    if "user_id" not in session or not session.get("2fa_required", False):
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user:
        flash("🫥 User not found. Please login again.")
        session.clear()  # Clearing the session for security
        return redirect(url_for("login"))

    form = TwoFactorForm()

    if form.validate_on_submit():
        verification_code = form.verification_code.data
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(verification_code):
            session["2fa_verified"] = True  # Set 2FA verification flag
            return redirect(url_for("inbox", username=user.primary_username))
        else:
            flash("⛔️ Invalid 2FA code. Please try again.")

    return render_template("verify_2fa_login.html", form=form)


@app.route("/logout")
@limiter.limit("120 per minute")
@require_2fa
def logout():
    # Explicitly remove specific session keys related to user authentication
    session.pop("user_id", None)
    session.pop("2fa_verified", None)

    # Clear the entire session to ensure no leftover data
    session.clear()

    # Flash a confirmation message for the user
    flash("👋 You have been logged out successfully.", "info")

    # Redirect to the login page or home page after logout
    return redirect(url_for("index"))


############################################################################################################
############################################################################################################

# SETTINGS

############################################################################################################
############################################################################################################


@app.route("/settings", methods=["GET", "POST"])
@limiter.limit("120 per minute")
@require_2fa
def settings():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    if not user:
        flash("🫥 User not found.")
        return redirect(url_for("login"))

    # Fetch all secondary usernames for the current user
    secondary_usernames = SecondaryUser.query.filter_by(user_id=user.id).all()

    # Initialize forms
    change_password_form = ChangePasswordForm()
    change_username_form = ChangeUsernameForm()
    smtp_settings_form = SMTPSettingsForm()
    pgp_key_form = PGPKeyForm()
    display_name_form = DisplayNameForm()

    # Additional admin-specific data initialization
    user_count = (
        two_fa_count
    ) = pgp_key_count = two_fa_percentage = pgp_key_percentage = None
    all_users = []

    # Check if user is admin and add admin-specific data
    if user.is_admin:
        user_count = User.query.count()
        two_fa_count = User.query.filter(User._totp_secret != None).count()
        pgp_key_count = (
            User.query.filter(User._pgp_key != None).filter(User._pgp_key != "").count()
        )
        two_fa_percentage = (two_fa_count / user_count * 100) if user_count else 0
        pgp_key_percentage = (pgp_key_count / user_count * 100) if user_count else 0
        all_users = User.query.all()  # Fetch all users for admin

    # Handle form submissions
    if request.method == "POST":
        # Handle Display Name Form Submission
        if (
            "update_display_name" in request.form
            and display_name_form.validate_on_submit()
        ):
            user.update_display_name(display_name_form.display_name.data.strip())
            db.session.commit()
            flash("👍 Display name updated successfully.")
            app.logger.debug(
                f"Display name updated to {user.display_name}, Verification status: {user.is_verified}"
            )
            return redirect(url_for("settings"))

        # Handle Change Username Form Submission
        elif (
            "change_username" in request.form
            and change_username_form.validate_on_submit()
        ):
            new_username = change_username_form.new_username.data
            existing_user = User.query.filter_by(primary_username=new_username).first()
            if existing_user:
                flash("💔 This username is already taken.")
            else:
                user.update_username(new_username)
                db.session.commit()
                session["username"] = new_username  # Update username in session
                flash("👍 Username changed successfully.")
                app.logger.debug(
                    f"Username updated to {user.primary_username}, Verification status: {user.is_verified}"
                )
            return redirect(url_for("settings"))

        # Handle SMTP Settings Form Submission
        elif smtp_settings_form.validate_on_submit():
            user.email = smtp_settings_form.smtp_username.data
            user.smtp_server = smtp_settings_form.smtp_server.data
            user.smtp_port = smtp_settings_form.smtp_port.data
            user.smtp_username = smtp_settings_form.smtp_username.data
            user.smtp_password = smtp_settings_form.smtp_password.data
            db.session.commit()
            flash("👍 SMTP settings updated successfully.")
            return redirect(url_for("settings"))

        # Handle PGP Key Form Submission
        elif pgp_key_form.validate_on_submit():
            user.pgp_key = pgp_key_form.pgp_key.data
            db.session.commit()
            flash("👍 PGP key updated successfully.")
            return redirect(url_for("settings"))

        # Handle Change Password Form Submission
        elif change_password_form.validate_on_submit():
            if bcrypt.check_password_hash(
                user.password_hash, change_password_form.old_password.data
            ):
                user.password_hash = bcrypt.generate_password_hash(
                    change_password_form.new_password.data
                ).decode("utf-8")
                db.session.commit()
                flash("👍 Password changed successfully.")
            else:
                flash("⛔️ Incorrect old password.")
            return redirect(url_for("settings"))

        # Check if user is admin and add admin-specific data
        is_admin = user.is_admin
        if is_admin:
            user_count = User.query.count()
            two_fa_count = User.query.filter(User._totp_secret != None).count()
            pgp_key_count = (
                User.query.filter(User._pgp_key != None)
                .filter(User._pgp_key != "")
                .count()
            )
            two_fa_percentage = (two_fa_count / user_count * 100) if user_count else 0
            pgp_key_percentage = (pgp_key_count / user_count * 100) if user_count else 0
        else:
            user_count = (
                two_fa_count
            ) = pgp_key_count = two_fa_percentage = pgp_key_percentage = None

    # Prepopulate form fields
    smtp_settings_form.smtp_server.data = user.smtp_server
    smtp_settings_form.smtp_port.data = user.smtp_port
    smtp_settings_form.smtp_username.data = user.smtp_username
    pgp_key_form.pgp_key.data = user.pgp_key
    display_name_form.display_name.data = user.display_name or user.primary_username

    return render_template(
        "settings.html",
        now=datetime.utcnow(),
        user=user,
        secondary_usernames=secondary_usernames,
        all_users=all_users,  # Pass to the template for admin view
        smtp_settings_form=smtp_settings_form,
        change_password_form=change_password_form,
        change_username_form=change_username_form,
        pgp_key_form=pgp_key_form,
        display_name_form=display_name_form,
        # Admin-specific data passed to the template
        is_admin=user.is_admin,
        user_count=user_count,
        two_fa_count=two_fa_count,
        pgp_key_count=pgp_key_count,
        two_fa_percentage=two_fa_percentage,
        pgp_key_percentage=pgp_key_percentage,
    )


@app.route("/toggle-2fa", methods=["POST"])
@limiter.limit("120 per minute")
def toggle_2fa():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = db.session.get(User, user_id)
    if user.totp_secret:
        return redirect(url_for("disable_2fa"))
    else:
        return redirect(url_for("enable_2fa"))


@app.route("/change-password", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def change_password():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    change_password_form = ChangePasswordForm(request.form)
    change_username_form = ChangeUsernameForm()
    smtp_settings_form = SMTPSettingsForm()
    pgp_key_form = PGPKeyForm()
    display_name_form = DisplayNameForm()

    if change_password_form.validate_on_submit():
        old_password = change_password_form.old_password.data
        new_password = change_password_form.new_password.data

        if bcrypt.check_password_hash(user.password_hash, old_password):
            user.password_hash = bcrypt.generate_password_hash(new_password).decode(
                "utf-8"
            )
            db.session.commit()
            session.clear()  # Clears the session, logging the user out
            flash(
                "👍 Password successfully changed. Please log in with your new password.",
                "success",
            )
            return redirect(
                url_for("login")
            )  # Redirect to the login page for re-authentication
        else:
            flash("⛔️ Incorrect old password.")

    # If not changing the password or if validation fails, render the settings page with all forms
    return render_template(
        "settings.html",
        change_password_form=change_password_form,
        change_username_form=change_username_form,
        smtp_settings_form=smtp_settings_form,
        pgp_key_form=pgp_key_form,
        display_name_form=display_name_form,
        user=user,
    )


@app.route("/change-username", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def change_username():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to continue.", "info")
        return redirect(url_for("login"))

    new_username = request.form.get("new_username").strip()
    if not new_username:
        flash("No new username provided.", "error")
        return redirect(url_for("settings"))

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("login"))

    if user.primary_username == new_username:
        flash("New username is the same as the current username.", "info")
        return redirect(url_for("settings"))

    existing_user = User.query.filter_by(primary_username=new_username).first()
    if existing_user:
        flash("This username is already taken.", "error")
        return redirect(url_for("settings"))

    # Log before updating
    app.logger.debug(
        f"Updating username for user ID {user_id}: {user.primary_username} to {new_username}"
    )

    # Directly update the user's primary username
    user.primary_username = new_username
    try:
        db.session.commit()
        # Important: Update the session with the new username
        session[
            "username"
        ] = new_username  # Ensure this key matches how you reference the username in your session
        flash("Username successfully changed.", "success")
        app.logger.debug(
            f"Username successfully updated for user ID {user_id} to {new_username}"
        )
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating username for user ID {user_id}: {e}")
        flash("An error occurred while updating the username.", "error")

    return redirect(url_for("settings"))


@app.route("/enable-2fa", methods=["GET", "POST"])
@limiter.limit("120 per minute")
def enable_2fa():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    form = TwoFactorForm()

    if form.validate_on_submit():
        verification_code = form.verification_code.data
        temp_totp_secret = session.get("temp_totp_secret")
        if temp_totp_secret and pyotp.TOTP(temp_totp_secret).verify(verification_code):
            user.totp_secret = temp_totp_secret
            db.session.commit()
            session.pop("temp_totp_secret", None)
            flash("👍 2FA setup successful. Please log in again with 2FA.")
            return redirect(url_for("logout"))  # Redirect to logout
        else:
            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for("enable_2fa"))

    # Generate new 2FA secret and QR code
    temp_totp_secret = pyotp.random_base32()
    session["temp_totp_secret"] = temp_totp_secret
    session["is_setting_up_2fa"] = True
    totp_uri = pyotp.totp.TOTP(temp_totp_secret).provisioning_uri(
        name=user.primary_username, issuer_name="HushLine"
    )
    img = qrcode.make(totp_uri)
    buffered = io.BytesIO()
    img.save(buffered)
    qr_code_img = (
        "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()
    )

    # Pass the text-based pairing code and the user to the template
    return render_template(
        "enable_2fa.html",
        form=form,
        qr_code_img=qr_code_img,
        text_code=temp_totp_secret,
        user=user,
    )


@app.route("/disable-2fa", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def disable_2fa():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = db.session.get(User, user_id)
    user.totp_secret = None
    db.session.commit()
    flash("🔓 2FA has been disabled.")
    return redirect(url_for("settings"))


@app.route("/confirm-disable-2fa", methods=["GET"])
def confirm_disable_2fa():
    return render_template("confirm_disable_2fa.html")


@app.route("/show-qr-code")
@limiter.limit("120 per minute")
@require_2fa
def show_qr_code():
    user = User.query.get(session["user_id"])
    if not user or not user.totp_secret:
        return redirect(url_for("enable_2fa"))

    form = TwoFactorForm()

    totp_uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
        name=user.primary_username, issuer_name="Hush Line"
    )
    img = qrcode.make(totp_uri)

    # Convert QR code to a data URI
    buffered = io.BytesIO()
    img.save(buffered)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    qr_code_img = f"data:image/png;base64,{img_str}"

    return render_template(
        "show_qr_code.html",
        form=form,
        qr_code_img=qr_code_img,
        user_secret=user.totp_secret,
    )


@app.route("/verify-2fa-setup", methods=["POST"])
@limiter.limit("120 per minute")
def verify_2fa_setup():
    user = User.query.get(session["user_id"])
    if not user:
        return redirect(url_for("login"))

    verification_code = request.form["verification_code"]
    totp = pyotp.TOTP(user.totp_secret)
    if totp.verify(verification_code):
        flash("👍 2FA setup successful. Please log in again.")
        session.pop("is_setting_up_2fa", None)
        return redirect(url_for("logout"))
    else:
        flash("⛔️ Invalid 2FA code. Please try again.")
        return redirect(url_for("show_qr_code"))


@app.route("/update_pgp_key", methods=["GET", "POST"])
@limiter.limit("120 per minute")
@require_2fa
def update_pgp_key():
    user_id = session.get("user_id")
    if not user_id:
        flash("⛔️ User not authenticated.")
        return redirect(url_for("login"))

    user = db.session.get(User, user_id)
    form = PGPKeyForm()
    if form.validate_on_submit():
        pgp_key = form.pgp_key.data

        if pgp_key.strip() == "":
            # If the field is empty, remove the PGP key
            user.pgp_key = None
        elif is_valid_pgp_key(pgp_key):
            # If the field is not empty and the key is valid, update the PGP key
            user.pgp_key = pgp_key
        else:
            # If the PGP key is invalid
            flash("⛔️ Invalid PGP key format or import failed.")
            return redirect(url_for("settings"))

        db.session.commit()
        flash("👍 PGP key updated successfully.")
        return redirect(url_for("settings"))
    return render_template("settings.html", form=form)


@app.route("/update_smtp_settings", methods=["GET", "POST"])
@limiter.limit("120 per minute")
@require_2fa
def update_smtp_settings():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = db.session.get(User, user_id)
    if not user:
        flash("⛔️ User not found")
        return redirect(url_for("settings"))

    # Initialize forms
    change_password_form = ChangePasswordForm()
    change_username_form = ChangeUsernameForm()
    smtp_settings_form = SMTPSettingsForm()
    pgp_key_form = PGPKeyForm()

    # Handling SMTP settings form submission
    if smtp_settings_form.validate_on_submit():
        # Updating SMTP settings from form data
        user.email = smtp_settings_form.smtp_username.data
        user.smtp_server = smtp_settings_form.smtp_server.data
        user.smtp_port = smtp_settings_form.smtp_port.data
        user.smtp_username = smtp_settings_form.smtp_username.data
        user.smtp_password = smtp_settings_form.smtp_password.data

        db.session.commit()
        flash("👍 SMTP settings updated successfully")
        return redirect(url_for("settings"))

    # Prepopulate SMTP settings form fields
    smtp_settings_form.email.data = user.email
    smtp_settings_form.smtp_server.data = user.smtp_server
    smtp_settings_form.smtp_port.data = user.smtp_port
    smtp_settings_form.smtp_username.data = user.smtp_username
    # Note: Password fields are typically not prepopulated for security reasons

    pgp_key_form.pgp_key.data = user.pgp_key

    return render_template(
        "settings.html",
        user=user,
        smtp_settings_form=smtp_settings_form,
        change_password_form=change_password_form,
        change_username_form=change_username_form,
        pgp_key_form=pgp_key_form,
    )


@app.route("/delete-account", methods=["POST"])
@require_2fa
def delete_account():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to continue.")
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    if user:
        # Explicitly delete messages for the user
        Message.query.filter_by(user_id=user.id).delete()

        # Explicitly delete secondary users if necessary
        SecondaryUser.query.filter_by(user_id=user.id).delete()

        # Now delete the user
        db.session.delete(user)
        db.session.commit()

        session.clear()  # Clear the session
        flash("🔥 Your account and all related information have been deleted.")
        return redirect(url_for("index"))
    else:
        flash("User not found. Please log in again.")
        return redirect(url_for("login"))


############################################################################################################
############################################################################################################

# PAID FEATURES

############################################################################################################
############################################################################################################


@app.route("/add-secondary-username", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def add_secondary_username():
    user_id = session.get("user_id")
    if not user_id:
        flash("👉 Please log in to continue.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    if not user:
        flash("🫥 User not found.", "error")
        return redirect(url_for("logout"))

    # Check if the user has paid for the premium feature
    if not user.has_paid:
        flash(
            "⚠️ This feature requires a paid account.",
            "warning",
        )
        return redirect(url_for("create_checkout_session"))

    # Check if the user already has the maximum number of secondary usernames
    if len(user.secondary_users) >= 5:
        flash("⚠️ You have reached the maximum number of secondary usernames.", "error")
        return redirect(url_for("settings"))

    username = request.form.get("username").strip()
    if not username:
        flash("⛔️ Username is required.", "error")
        return redirect(url_for("settings"))

    # Check if the secondary username is already taken
    existing_user = SecondaryUser.query.filter_by(username=username).first()
    if existing_user:
        flash("⚠️ This username is already taken.", "error")
        return redirect(url_for("settings"))

    # Add the new secondary username
    new_secondary_user = SecondaryUser(username=username, user_id=user.id)
    db.session.add(new_secondary_user)
    db.session.commit()
    flash("👍 Username added successfully.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/secondary/<secondary_username>/update", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def update_secondary_username(secondary_username):
    # Ensure the user is logged in
    user_id = session.get("user_id")
    if not user_id:
        flash("👉 Please log in to continue.", "warning")
        return redirect(url_for("login"))

    # Find the secondary user in the database
    secondary_user = SecondaryUser.query.filter_by(
        username=secondary_username, user_id=user_id
    ).first_or_404()

    # Update the secondary user's display name from the form data
    new_display_name = request.form.get("display_name").strip()
    if new_display_name:
        secondary_user.display_name = new_display_name
        db.session.commit()
        flash("Display name updated successfully.", "success")
    else:
        flash("Display name cannot be empty.", "error")

    # Redirect back to the settings page for the secondary user
    return redirect(
        url_for("secondary_user_settings", secondary_username=secondary_username)
    )


@app.route("/settings/secondary/<secondary_username>", methods=["GET", "POST"])
@limiter.limit("120 per minute")
@require_2fa
def secondary_user_settings(secondary_username):
    # Ensure the user is logged in
    user_id = session.get("user_id")
    if not user_id:
        flash("👉 Please log in to continue.", "warning")
        return redirect(url_for("login"))

    # Retrieve the primary user
    user = User.query.get(user_id)

    # Find the secondary user in the database
    secondary_user = SecondaryUser.query.filter_by(
        username=secondary_username, user_id=user_id
    ).first_or_404()

    if request.method == "POST":
        # Update the secondary user's display name or other settings
        new_display_name = request.form.get("display_name", "").strip()
        if new_display_name:
            secondary_user.display_name = new_display_name
            db.session.commit()
            flash("👍 Settings updated successfully.")
        else:
            flash("Display name cannot be empty.", "error")

    return render_template(
        "secondary_user_settings.html", user=user, secondary_user=secondary_user
    )


@app.route("/create-checkout-session", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def create_checkout_session():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        # Create or update Stripe Customer and store the Stripe Customer ID
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(email=user.email)
            user.stripe_customer_id = customer.id
            db.session.commit()
        else:
            customer = stripe.Customer.retrieve(user.stripe_customer_id)

        # Store the origin page in the session
        origin_page = request.referrer or url_for("index")
        session["origin_page"] = origin_page

        # price_id = "price_1OhiU5LcBPqjxU07a4eKQHrO"  # Test
        price_id = "price_1OhhYFLcBPqjxU07u2wYbUcF"

        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=url_for("payment_success", _external=True)
            + f"?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=url_for("payment_cancel", _external=True)
            + f"?session_id={{CHECKOUT_SESSION_ID}}",
        )
        return jsonify({"id": checkout_session.id})
    except Exception:
        app.logger.error("Failed to create checkout session", exc_info=True)
        return (
            jsonify({"error": "An error occurred while processing your request"}),
            500,
        )


@app.route("/payment-success")
@limiter.limit("120 per minute")
@require_2fa
def payment_success():
    session_id = request.args.get("session_id")

    if "user_id" in session:
        user_id = session["user_id"]
        user = User.query.get(user_id)
        if user:
            try:
                checkout_session = stripe.checkout.Session.retrieve(session_id)
                subscription = stripe.Subscription.retrieve(
                    checkout_session.subscription
                )

                # Update user's subscription details
                user.has_paid = True
                user.stripe_subscription_id = subscription.id
                user.paid_features_expiry = datetime.fromtimestamp(
                    subscription.current_period_end
                )

                user.is_subscription_active = True
                db.session.commit()
                flash(
                    "🎉 Payment successful! Your account has been upgraded.", "success"
                )
            except Exception as e:
                app.logger.error(f"Failed to retrieve subscription details: {e}")
                flash("An error occurred while processing your payment.", "error")
        else:
            flash("🫥 User not found.", "error")
    else:
        flash("⛔️ You are not logged in.", "warning")

    origin_page = request.args.get("origin", url_for("index"))
    if is_safe_url(origin_page):
        return redirect(origin_page)
    else:
        flash("Warning: Unsafe redirect attempt detected.", "warning")
        return redirect(url_for("index"))


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("", "http", "https")
        and ref_url.netloc == test_url.netloc
        and test_url.path.startswith("/")
    )


@app.route("/payment-cancel")
@limiter.limit("120 per minute")
@require_2fa
def payment_cancel():
    origin_page = request.args.get("origin", url_for("index"))
    if is_safe_url(origin_page):
        flash("👍 Payment was cancelled.", "warning")
        return redirect(origin_page)
    else:
        flash("Warning: Unsafe redirect attempt detected.", "warning")
        return redirect(url_for("index"))


@app.route("/stripe-webhook", methods=["POST"])
@require_2fa
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )

        # Handle the checkout.session.completed event
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user = find_user_by_stripe_customer_id(session["customer"])
            if user:
                user.has_paid = True
                db.session.commit()

        # Handle the customer.subscription.deleted event
        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            user = find_user_by_stripe_customer_id(subscription["customer"])
            if user:
                # Use the subscription's current period end for paid_features_expiry
                user.paid_features_expiry = datetime.utcfromtimestamp(
                    subscription["current_period_end"]
                )
                user.is_subscription_active = False
                db.session.commit()

        # Handle the invoice.payment_failed event
        elif event["type"] == "invoice.payment_failed":
            invoice = event["data"]["object"]
            user = find_user_by_stripe_customer_id(invoice["customer"])
            if user:
                user.has_paid = False
                db.session.commit()

        return jsonify({"status": "success"})
    except ValueError:
        # Invalid payload
        app.logger.error("Invalid payload received from Stripe webhook.", exc_info=True)
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        app.logger.error("Invalid signature for Stripe webhook.", exc_info=True)
        return jsonify({"error": "Invalid signature"}), 400
    except Exception as e:
        # Other exceptions
        app.logger.error("Error processing Stripe webhook.", exc_info=True)
        return jsonify({"error": "An error occurred"}), 400


def find_user_by_stripe_customer_id(customer_id):
    return User.query.filter_by(stripe_customer_id=customer_id).first()


@app.route("/cancel-subscription", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def cancel_subscription():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    if not user or not user.stripe_subscription_id:
        flash("Subscription not found.", "error")
        return redirect(url_for("settings"))

    try:
        # Cancel the subscription on Stripe
        stripe.Subscription.delete(user.stripe_subscription_id)

        # Update the database to reflect the subscription's end date
        subscription = stripe.Subscription.retrieve(user.stripe_subscription_id)
        user.is_subscription_active = False
        user.paid_features_expiry = datetime.fromtimestamp(
            subscription.current_period_end
        )
        db.session.commit()

        flash(
            "Your subscription has been canceled. You will retain access to paid features until the end of your billing period.",
            "success",
        )
    except Exception as e:
        app.logger.error(f"Failed to cancel subscription: {e}")
        flash(
            "An error occurred while attempting to cancel your subscription.", "error"
        )

    return redirect(url_for("settings"))


def has_paid_features(user_id):
    user = User.query.get(user_id)
    if (
        user
        and user.paid_features_expiry
        and user.paid_features_expiry > datetime.utcnow()
    ):
        return True
    return False


############################################################################################################
############################################################################################################

# ADMIN
# Utilities for admins. Toggling paid features, admin privileges, and verification status.

############################################################################################################
############################################################################################################


@app.route("/admin/toggle_verified/<int:user_id>", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def toggle_verified(user_id):
    if not session.get("is_admin", False):
        flash("Unauthorized access.", "error")
        return redirect(url_for("settings"))

    user = User.query.get_or_404(user_id)
    user.is_verified = not user.is_verified
    db.session.commit()
    flash("✅ User verification status toggled.", "success")
    return redirect(url_for("settings"))


@app.route("/admin/toggle_paid/<int:user_id>", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def toggle_paid(user_id):
    if not session.get("is_admin", False):
        flash("Unauthorized access.", "error")
        return redirect(url_for("settings"))

    user = User.query.get_or_404(user_id)
    user.has_paid = not user.has_paid
    db.session.commit()
    flash("✅ User payment status toggled.", "success")
    return redirect(url_for("settings"))


@app.route("/admin/toggle_admin/<int:user_id>", methods=["POST"])
@limiter.limit("120 per minute")
@require_2fa
def toggle_admin(user_id):
    if not session.get("is_admin", False):
        flash("Unauthorized access.", "error")
        return redirect(url_for("settings"))

    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash("✅ User admin status toggled.", "success")
    return redirect(url_for("settings"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()
