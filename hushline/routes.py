import logging
import os
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import pyotp
import stripe
from flask import (
    Flask,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from sqlalchemy import event
from wtforms import PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from .crypto import encrypt_message
from .db import db
from .forms import ComplexPassword
from .limiter import limiter
from .model import InviteCode, Message, SecondaryUsername, User
from .utils import generate_user_directory_json, require_2fa, send_email

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


def valid_username(form, field):
    if not re.match(r"^[a-zA-Z0-9_-]+$", field.data):
        raise ValidationError(
            "Username must contain only letters, numbers, underscores, or hyphens."
        )


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])


class MessageForm(FlaskForm):
    contact_method = StringField(
        "Contact Method",
        validators=[Optional(), Length(max=255)],  # Optional if you want it to be non-mandatory
    )
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
    )


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=25), valid_username]
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )
    invite_code = StringField("Invite Code", validators=[DataRequired(), Length(min=6, max=25)])


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


def init_app(app: Flask) -> None:
    stripe.api_key = app.config.get("STRIPE_API_KEY")

    @app.route("/")
    @limiter.limit("120 per minute")
    def index() -> Response:
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            if user:
                return redirect(url_for("inbox", username=user.primary_username))
            else:
                flash("🫥 User not found. Please log in again.")
                session.pop("user_id", None)  # Clear the invalid user_id from session
                return redirect(url_for("login"))
        else:
            return redirect(url_for("directory"))

    @app.route("/inbox")
    @limiter.limit("120 per minute")
    @require_2fa
    def inbox() -> Response | str:
        # Redirect if not logged in
        if "user_id" not in session:
            flash("Please log in to access your inbox.")
            return redirect(url_for("login"))

        logged_in_user_id = session["user_id"]
        requested_username = request.args.get("username")
        logged_in_username = User.query.get(logged_in_user_id).primary_username

        if requested_username and requested_username != logged_in_username:
            return redirect(url_for("inbox"))

        primary_user = User.query.get(logged_in_user_id)
        messages = (
            Message.query.filter_by(user_id=primary_user.id).order_by(Message.id.desc()).all()
        )
        secondary_usernames_dict = {su.id: su for su in primary_user.secondary_usernames}

        return render_template(
            "inbox.html",
            user=primary_user,
            secondary_username=None,
            messages=messages,
            is_secondary=False,
            secondary_usernames=secondary_usernames_dict,
        )

    @app.route("/submit_message/<username>", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def submit_message(username: str) -> Response | str:
        form = MessageForm()

        # Try to get the user either by primary or secondary username
        user = User.query.filter_by(primary_username=username).first()
        secondary_user = None
        display_name_or_username = ""

        if user:
            display_name_or_username = user.display_name or user.primary_username
        else:
            # If not found, check in secondary usernames
            secondary_user = SecondaryUsername.query.filter_by(username=username).first()
            if secondary_user:
                user = secondary_user.primary_user
                display_name_or_username = secondary_user.display_name or secondary_user.username
                # Check if the subscription has expired for secondary usernames
                if not user.has_paid or user.paid_features_expiry < datetime.utcnow():
                    flash("🫥 User not found.")
                    return redirect(url_for("index"))

        if not user:
            flash("User not found.")
            return redirect(url_for("index"))

        if form.validate_on_submit():
            content = form.content.data
            contact_method = form.contact_method.data.strip() if form.contact_method.data else ""
            full_content = (
                f"Contact Method: {contact_method}\n\n{content}" if contact_method else content
            )
            client_side_encrypted = request.form.get("client_side_encrypted", "false") == "true"

            if client_side_encrypted:
                content_to_save = (
                    content  # Assume content is already encrypted and includes contact method
                )
            elif user.pgp_key:
                try:
                    encrypted_content = encrypt_message(full_content, user.pgp_key)
                    if not encrypted_content:
                        flash("Failed to encrypt message with PGP key.", "error")
                        return redirect(url_for("submit_message", username=username))
                    content_to_save = encrypted_content
                except Exception as e:
                    app.logger.error("Encryption failed: %s", str(e), exc_info=True)
                    flash("Failed to encrypt message due to an error.", "error")
                    return redirect(url_for("submit_message", username=username))
            else:
                content_to_save = full_content

            # Save the new message
            new_message = Message(
                content=email_content,
                user_id=user.id,
                secondary_user_id=secondary_user.id if secondary_user else None,
            )
            db.session.add(new_message)
            db.session.commit()

            if (
                user.email
                and user.smtp_server
                and user.smtp_port
                and user.smtp_username
                and user.smtp_password
                and content_to_save
            ):
                try:
                    sender_email = user.smtp_username
                    email_sent = send_email(
                        user.email, "New Message", content_to_save, user, sender_email
                    )
                    flash_message = (
                        "Message submitted and email sent successfully."
                        if email_sent
                        else "Message submitted, but failed to send email."
                    )
                    flash(flash_message)
                except Exception as e:
                    app.logger.error(f"Error sending email: {str(e)}", exc_info=True)
                    flash(
                        "Message submitted, but an error occurred while sending email.", "warning"
                    )
            else:
                flash("Message submitted successfully.")

            return redirect(url_for("submit_message", username=username))

        return render_template(
            "submit_message.html",
            form=form,
            user=user,
            secondary_user=secondary_user,
            username=username,
            display_name_or_username=user.display_name or user.primary_username,
            current_user_id=session.get("user_id"),
            public_key=user.pgp_key,
        )

    @app.route("/delete_message/<int:message_id>", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def delete_message(message_id: int) -> Response:
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
            return redirect(url_for("inbox", username=user.primary_username))
        else:
            flash("⛔️ Message not found or unauthorized access.")
            return redirect(url_for("inbox", username=user.primary_username))

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def register() -> Response | str:
        require_invite_code = os.environ.get("REGISTRATION_CODES_REQUIRED", "True") == "True"
        form = RegistrationForm()
        if not require_invite_code:
            del form.invite_code

        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data

            invite_code_input = form.invite_code.data if require_invite_code else None
            if invite_code_input:
                invite_code = InviteCode.query.filter_by(code=invite_code_input).first()
                if not invite_code or invite_code.expiration_date < datetime.utcnow():
                    flash("⛔️ Invalid or expired invite code.", "error")
                    return (
                        render_template(
                            "register.html",
                            form=form,
                            require_invite_code=require_invite_code,
                        ),
                        400,
                    )

            if User.query.filter_by(primary_username=username).first():
                flash("💔 Username already taken.", "error")
                return (
                    render_template(
                        "register.html",
                        form=form,
                        require_invite_code=require_invite_code,
                    ),
                    409,
                )

            # Create new user instance
            new_user = User(primary_username=username)
            new_user.password_hash = password  # This triggers the password_hash setter
            db.session.add(new_user)
            db.session.commit()

            flash("👍 Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html", form=form, require_invite_code=require_invite_code)

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def login() -> Response | str:
        form = LoginForm()
        if request.method == "POST":
            if form.validate_on_submit():
                username = form.username.data.strip()
                password = form.password.data

                user = User.query.filter_by(primary_username=username).first()

                if user and user.check_password(password):
                    session.permanent = True
                    session["user_id"] = user.id
                    session["username"] = user.primary_username
                    session["is_authenticated"] = True
                    session["2fa_required"] = user.totp_secret is not None
                    session["2fa_verified"] = False
                    session["is_admin"] = user.is_admin

                    if user.totp_secret:
                        return redirect(url_for("verify_2fa_login"))
                    else:
                        session["2fa_verified"] = True
                        return redirect(url_for("inbox", username=user.primary_username))
                else:
                    flash("⛔️ Invalid username or password")
        return render_template("login.html", form=form)

    @app.route("/verify-2fa-login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def verify_2fa_login() -> Response | str:
        # Redirect to login if user is not authenticated or 2FA is not required
        if "user_id" not in session or not session.get("2fa_required", False):
            flash("You need to log in first.")
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
                return render_template("verify_2fa_login.html", form=form), 401

        return render_template("verify_2fa_login.html", form=form)

    @app.route("/logout")
    @limiter.limit("120 per minute")
    @require_2fa
    def logout() -> Response:
        # Explicitly remove specific session keys related to user authentication
        session.pop("user_id", None)
        session.pop("2fa_verified", None)

        # Clear the entire session to ensure no leftover data
        session.clear()

        # Flash a confirmation message for the user
        flash("👋 You have been logged out successfully.", "info")

        # Redirect to the login page or home page after logout
        return redirect(url_for("index"))

    @app.route("/settings/update_directory_visibility", methods=["POST"])
    def update_directory_visibility():
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            user.show_in_directory = "show_in_directory" in request.form
            db.session.commit()
            flash("Directory visibility updated.")
        else:
            flash("You need to be logged in to update settings.")
        return redirect(url_for("settings.index"))

    def sort_users_by_display_name(users, admin_first=True):
        if admin_first:
            # Sorts admins to the top, then by display name or username
            return sorted(
                users,
                key=lambda u: (
                    not u.is_admin,
                    (u.display_name or u.primary_username).strip().lower(),
                ),
            )
        else:
            # Sorts only by display name or username
            return sorted(
                users,
                key=lambda u: (u.display_name or u.primary_username).strip().lower(),
            )

    @app.route("/directory")
    def directory():
        logged_in = "user_id" in session
        users = User.query.all()  # Fetch all users
        sorted_users = sort_users_by_display_name(
            users, admin_first=True
        )  # Sort users in Python with admins first
        return render_template("directory.html", users=sorted_users, logged_in=logged_in)

    @event.listens_for(User, "after_update")
    def receive_after_update(mapper, connection, target):
        current_app.logger.info("Triggering JSON regeneration due to user update/insert")
        generate_user_directory_json()

    # Stripe Checkout session creation
    @app.route("/create-checkout-session", methods=["POST"])
    def create_checkout_session():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "User not authenticated"}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        try:
            if not user.stripe_customer_id:
                customer = stripe.Customer.create(email=user.email)
                user.stripe_customer_id = customer.id
                db.session.commit()
            else:
                customer = stripe.Customer.retrieve(user.stripe_customer_id)

            checkout_session = stripe.checkout.Session.create(
                customer=user.stripe_customer_id,
                payment_method_types=["card"],
                line_items=[{"price": "price_1OhhYFLcBPqjxU07u2wYbUcF", "quantity": 1}],
                mode="subscription",
                success_url=url_for("payment_success", _external=True)
                + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=url_for("payment_cancel", _external=True),
            )
            return jsonify({"id": checkout_session.id})
        except Exception as e:
            app.logger.error(f"Failed to create checkout session: {str(e)}")
            return jsonify({"error": "Failed to create checkout session", "details": str(e)}), 500

    # Handling successful payment
    @app.route("/payment-success")
    def payment_success():
        session_id = request.args.get("session_id")
        user_id = session.get("user_id")
        if not user_id:
            flash("⛔️ You are not logged in.", "warning")
            return redirect(url_for("login"))

        user = User.query.get(user_id)
        if user:
            try:
                checkout_session = stripe.checkout.Session.retrieve(session_id)
                subscription = stripe.Subscription.retrieve(checkout_session.subscription)

                # Update user's subscription details
                user.has_paid = True
                user.stripe_subscription_id = subscription.id
                user.paid_features_expiry = datetime.fromtimestamp(subscription.current_period_end)
                user.is_subscription_active = True
                db.session.commit()
                flash("🎉 Payment successful! Your account has been upgraded.", "success")
            except Exception as e:
                app.logger.error(f"Failed to retrieve subscription details: {e}")
                flash("An error occurred while processing your payment.", "error")
        else:
            flash("🫥 User not found.", "error")

        origin_page = request.args.get("origin", url_for("index"))
        return redirect(origin_page)

    # Ensure URLs are safe before redirecting
    def is_safe_url(target):
        ref_url = urlparse(request.host_url)
        test_url = urlparse(urljoin(request.host_url, target))
        return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc

    @app.route("/payment-cancel")
    def payment_cancel():
        origin_page = request.args.get("origin", url_for("index"))
        if is_safe_url(origin_page):
            flash("👍 Payment was cancelled.", "warning")
            return redirect(origin_page)
        else:
            flash("Warning: Unsafe redirect attempt detected.", "warning")
            return redirect(url_for("index"))

    @app.route("/stripe-webhook", methods=["POST"])
    def stripe_webhook():
        payload = request.get_data(as_text=True)
        sig_header = request.headers.get("Stripe-Signature")
        endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)

            # Process the webhook event
            if event["type"] == "checkout.session.completed":
                session = event["data"]["object"]
                user = User.query.filter_by(stripe_customer_id=session["customer"]).first()
                if user:
                    user.has_paid = True
                    db.session.commit()

            return jsonify({"status": "success"}), 200

        except ValueError as e:
            app.logger.error(f"Invalid payload: {str(e)}")
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError as e:
            app.logger.error(f"Invalid signature: {str(e)}")
            return jsonify({"error": "Invalid signature"}), 400
        except Exception as e:
            app.logger.error(f"Unknown error: {str(e)}")
            return jsonify({"error": "Unknown error"}), 400

    def find_user_by_stripe_customer_id(customer_id):
        return User.query.filter_by(stripe_customer_id=customer_id).first()

    @app.route("/cancel-subscription", methods=["POST"])
    @require_2fa
    def cancel_subscription():
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))

        user = User.query.get(user_id)
        if not user or not user.stripe_subscription_id:
            flash("Subscription not found.", "error")
            return redirect(url_for("settings.index"))

        try:
            # Cancel the subscription on Stripe
            stripe.Subscription.delete(user.stripe_subscription_id)

            # Refresh the subscription info to ensure it's properly updated
            subscription = stripe.Subscription.retrieve(user.stripe_subscription_id)
            user.is_subscription_active = False
            user.paid_features_expiry = datetime.fromtimestamp(subscription.current_period_end)
            db.session.commit()

            flash(
                "Your subscription has been canceled. You will retain access to paid features until the end of your billing period.",  # noqa: E501
                "success",
            )
        except Exception as e:
            app.logger.error(f"Failed to cancel subscription: {str(e)}")
            flash("An error occurred while attempting to cancel your subscription.", "error")

        return redirect(url_for("settings.index"))

    def has_paid_features(user_id):
        user = User.query.get(user_id)
        if user and user.paid_features_expiry and user.paid_features_expiry > datetime.utcnow():
            return True
        return False

    @app.route("/add-secondary-username", methods=["POST"])
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
        if len(user.secondary_usernames) >= 5:
            flash("⚠️ You have reached the maximum number of secondary usernames.", "error")
            return redirect(url_for("settings.index"))

        username = request.form.get("username").strip()
        if not username:
            flash("⛔️ Username is required.", "error")
            return redirect(url_for("settings.index"))

        # Check if the secondary username is already taken
        existing_user = SecondaryUsername.query.filter_by(username=username).first()
        if existing_user:
            flash("⚠️ This username is already taken.", "error")
            return redirect(url_for("settings.index"))

        # Add the new secondary username
        new_secondary_user = SecondaryUsername(username=username, user_id=user.id)
        db.session.add(new_secondary_user)
        db.session.commit()
        flash("👍 Username added successfully.", "success")
        return redirect(url_for("settings.index"))

    @app.route("/settings/secondary/<secondary_username>/update", methods=["POST"])
    @require_2fa
    def update_secondary_username(secondary_username):
        # Ensure the user is logged in
        user_id = session.get("user_id")
        if not user_id:
            flash("👉 Please log in to continue.", "warning")
            return redirect(url_for("login"))

        # Find the secondary user in the database
        secondary_user = SecondaryUsername.query.filter_by(
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
        return redirect(url_for("secondary_user_settings", secondary_username=secondary_username))

    @app.route("/settings/secondary/<secondary_username>", methods=["GET", "POST"])
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
        secondary_user = SecondaryUsername.query.filter_by(
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

        # Pass the secondary user object correctly to the template
        return render_template(
            "secondary_user_settings.html",
            user=user,
            secondary_username=secondary_user,  # Ensure this variable name matches the expectation in your template  # noqa: E501
        )
