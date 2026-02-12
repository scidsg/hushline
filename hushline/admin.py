from flask import Blueprint, abort, current_app, flash, redirect, request, session, url_for
from flask_wtf.csrf import validate_csrf
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import Tier, User, Username
from hushline.premium import update_price
from hushline.user_deletion import delete_user_and_related, delete_username_and_related
from hushline.utils import parse_bool


def _parse_form_bool(field_name: str) -> bool:
    raw_value = request.form.get(field_name)
    if raw_value is None:
        abort(400)
    try:
        return parse_bool(raw_value)
    except ValueError:
        abort(400)


def _validate_csrf() -> None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return
    token = request.form.get("csrf_token")
    if not token:
        abort(400)
    try:
        validate_csrf(token)
    except ValidationError:
        abort(400)


def create_blueprint() -> Blueprint:
    bp = Blueprint("admin", __file__, url_prefix="/admin")

    @bp.route("/toggle_verified/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_verified(user_id: int) -> Response:
        _validate_csrf()
        if not current_app.config.get("USER_VERIFICATION_ENABLED"):
            abort(401)

        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        desired_verified = _parse_form_bool("is_verified")
        user.primary_username.is_verified = desired_verified
        db.session.commit()
        status_label = "verified" if desired_verified else "unverified"
        flash(f"✅ User verification set to {status_label}.", "success")
        return redirect(url_for("settings.admin"))

    @bp.route("/toggle_verified_username/<int:username_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_verified_username(username_id: int) -> Response:
        _validate_csrf()
        if not current_app.config.get("USER_VERIFICATION_ENABLED"):
            abort(401)

        username = db.session.get(Username, username_id)
        if username is None:
            abort(404)
        desired_verified = _parse_form_bool("is_verified")
        username.is_verified = desired_verified
        db.session.commit()
        status_label = "verified" if desired_verified else "unverified"
        flash(f"✅ Username verification set to {status_label}.", "success")
        return redirect(url_for("settings.admin"))

    @bp.route("/toggle_admin/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_admin(user_id: int) -> Response:
        _validate_csrf()
        # Use a database transaction
        with db.session.begin_nested():
            user = db.session.get(User, user_id)
            if user is None:
                abort(404)

            desired_admin = _parse_form_bool("is_admin")

            if user.is_admin and not desired_admin:
                # Re-check admin count within the transaction
                admin_count = db.session.query(User).filter_by(is_admin=True).count()
                if admin_count == 1:
                    flash("⛔️ You cannot remove the only admin")
                    return abort(400)

            # Set admin status explicitly
            user.is_admin = desired_admin

        # Commit the transaction
        db.session.commit()

        status_label = "admin" if desired_admin else "non-admin"
        flash(f"✅ User admin status set to {status_label}.", "success")
        return redirect(url_for("settings.admin"))

    @bp.route("/update_tier/<int:tier_id>", methods=["POST"])
    @admin_authentication_required
    def update_tier(tier_id: int) -> Response:
        _validate_csrf()
        tier = db.session.get(Tier, tier_id)
        if tier is None:
            abort(404)

        # Get monthly_price from the request
        monthly_price = request.form.get("monthly_price")
        if not monthly_price:
            flash("❌ Monthly price is required.", "danger")
            return redirect(url_for("settings.admin"))

        # Convert the monthly_price to a float
        try:
            monthly_price_number = float(monthly_price)
        except ValueError:
            flash("❌ Monthly price must be a number.", "danger")
            return redirect(url_for("settings.admin"))

        # Convert to cents
        monthly_amount = int(monthly_price_number * 100)

        # Update in the database
        tier.monthly_amount = monthly_amount
        db.session.commit()

        # Update in stripe
        update_price(tier)

        flash("✅ Price updated.", "success")
        return redirect(url_for("settings.admin"))

    @bp.route("/delete_user/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def delete_user(user_id: int) -> Response:
        _validate_csrf()
        if session.get("user_id") == user_id:
            flash("⛔️ You cannot delete your own account from the admin panel.", "danger")
            return abort(400)

        with db.session.begin_nested():
            user = db.session.get(User, user_id)
            if user is None:
                abort(404)

            delete_user_and_related(user)

        db.session.commit()
        flash("🔥 User account and all related information have been deleted.", "success")
        return redirect(url_for("settings.admin"))

    @bp.route("/delete_username/<int:username_id>", methods=["POST"])
    @admin_authentication_required
    def delete_username(username_id: int) -> Response:
        _validate_csrf()
        username = db.session.get(Username, username_id)
        if username is None:
            abort(404)

        if username.is_primary:
            flash("⛔️ You cannot delete a primary username here.", "danger")
            return abort(400)

        delete_username_and_related(username)
        db.session.commit()
        flash("🔥 Alias and related data have been deleted.", "success")
        return redirect(url_for("settings.admin"))

    return bp
