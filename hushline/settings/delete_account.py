from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import User
from hushline.user_deletion import (
    delete_user_and_related,
    has_deletion_blocking_stripe_invoice,
    has_deletion_blocking_stripe_invoice_event,
    has_deletion_blocking_stripe_subscription_event,
)


def register_delete_account_routes(bp: Blueprint) -> None:
    @bp.route("/delete-account", methods=["POST"])
    @authentication_required
    def delete_account() -> Response | str:
        with db.session.begin_nested():
            user = db.session.get(User, session["user_id"])
            if user:
                if user.is_admin:
                    admin_count = db.session.query(User).filter_by(is_admin=True).count()
                    if admin_count == 1:
                        flash("⛔️ You cannot delete the only admin account.")
                        return abort(400)

                if user.has_deletion_blocking_stripe_subscription:
                    flash(
                        "⛔️ Your account has an active or unresolved Stripe subscription. "
                        "Cancel the subscription and wait for Stripe to confirm cancellation "
                        "before deleting your account."
                    )
                    return abort(400)

                if has_deletion_blocking_stripe_invoice(user):
                    flash(
                        "⛔️ Your account has draft, open, or unknown Stripe invoices. "
                        "Resolve those invoices before deleting your account."
                    )
                    return abort(400)

                if has_deletion_blocking_stripe_invoice_event(user):
                    flash(
                        "⛔️ Your account has queued Stripe invoice webhooks. "
                        "Wait for those events to finish before deleting your account."
                    )
                    return abort(400)

                if has_deletion_blocking_stripe_subscription_event(user):
                    flash(
                        "⛔️ Your account has queued Stripe subscription webhooks. "
                        "Wait for those events to finish before deleting your account."
                    )
                    return abort(400)

                delete_user_and_related(user)
            else:
                flash("🫥 User not found. Please log in again.")
                return redirect(url_for("login"))

        db.session.commit()
        session.clear()
        flash("🔥 Your account and all related information have been deleted.")
        return redirect(url_for("index"))
