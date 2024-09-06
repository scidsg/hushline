from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from .db import db
from .model import Tier, User
from .stripe import create_subscription, get_latest_invoice_payment_intent_client_secret
from .utils import authentication_required

FREE_TIER = 1
BUSINESS_TIER = 2


def create_blueprint() -> Blueprint:
    bp = Blueprint("premium", __file__, url_prefix="/premium")

    @bp.route("/", methods=["GET"])
    @authentication_required
    def index() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        return render_template("premium.html", user=user)

    @bp.route("/upgrade", methods=["GET", "POST"])
    @authentication_required
    def upgrade() -> Response | str:
        if request.method == "GET":
            return redirect(url_for("premium.index"))

        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # If the user is already on the business tier
        if user.tier_id == BUSINESS_TIER:
            flash("👍 You're already upgraded.")
            return redirect(url_for("premium.index"))

        # Select the business tier
        business_tier = db.session.query(Tier).get(BUSINESS_TIER)
        if not business_tier:
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))

        # Subscribe the user to the business tier
        try:
            stripe_subscription = create_subscription(user, business_tier)
        except Exception as e:
            current_app.logger.error(f"Stripe error: {e}")
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))

        return render_template(
            "premium_subscribe.html",
            user=user,
            tier=business_tier,
            stripe_subscription_id=stripe_subscription.id,
            stripe_client_secret=get_latest_invoice_payment_intent_client_secret(
                stripe_subscription
            ),
            stripe_publishable_key=current_app.config.get("STRIPE_PUBLISHABLE_KEY"),
        )

    @bp.route("/downgrade", methods=["POST"])
    @authentication_required
    def downgrade() -> Response:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # user.premium = False
        # db.session.add(user)
        # db.session.commit()

        return redirect(url_for("premium.index"))

    return bp
