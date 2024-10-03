from flask import Blueprint, abort, flash, redirect, request, url_for
from werkzeug.wrappers.response import Response

from .db import db
from .model import Tier, User
from .premium import update_price
from .utils import admin_authentication_required


def create_blueprint() -> Blueprint:
    bp = Blueprint("admin", __file__, url_prefix="/admin")

    @bp.route("/toggle_verified/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_verified(user_id: int) -> Response:
        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        user.primary_username.is_verified = not user.primary_username.is_verified
        db.session.commit()
        flash("✅ User verification status toggled.", "success")
        return redirect(url_for("settings.index"))

    @bp.route("/toggle_admin/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_admin(user_id: int) -> Response:
        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        user.is_admin = not user.is_admin
        db.session.commit()
        flash("✅ User admin status toggled.", "success")
        return redirect(url_for("settings.index"))

    @bp.route("/update_tier/<int:tier_id>", methods=["POST"])
    @admin_authentication_required
    def update_tier(tier_id: int) -> Response:
        tier = db.session.get(Tier, tier_id)
        if tier is None:
            abort(404)

        # Get monthly_price from the request
        monthly_price = request.form.get("monthly_price")
        if not monthly_price:
            flash("❌ Monthly price is required.", "danger")
            return redirect(url_for("settings.index"))

        # Convert the monthly_price to a float
        try:
            monthly_price_number = float(monthly_price)
        except ValueError:
            flash("❌ Monthly price must be a number.", "danger")
            return redirect(url_for("settings.index"))

        # Convert to cents
        monthly_amount = int(monthly_price_number * 100)

        # Update in the database
        tier.monthly_amount = monthly_amount
        db.session.commit()

        # Update in stripe
        update_price(tier)

        flash("✅ Price updated.", "success")
        return redirect(url_for("settings.index"))

    return bp
