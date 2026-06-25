from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    session,
)
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import AccountCategory, User, Username
from hushline.user_deletion import (
    deletion_blocking_stripe_invoice_counts_by_user_ids,
    deletion_blocking_stripe_invoice_event_counts_by_user_ids,
    deletion_blocking_stripe_subscription_event_counts_by_user_ids,
    stripe_invoice_counts_by_user_ids,
)

ADMIN_USERNAMES_PER_PAGE = 20


def register_admin_routes(bp: Blueprint) -> None:
    @bp.route("/admin")
    @admin_authentication_required
    def admin() -> str:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        search_query = (request.args.get("q") or "").strip()
        requested_page = request.args.get("page", "1")
        try:
            current_page = max(1, int(requested_page))
        except ValueError:
            current_page = 1

        username_filter = None
        if search_query:
            search_pattern = f"%{search_query}%"
            username_filter = or_(
                Username._username.ilike(search_pattern),
                Username._display_name.ilike(search_pattern),
                User.account_category.ilike(search_pattern),
            )

        username_count_query = (
            db.select(func.count(Username.id)).select_from(Username).outerjoin(User)
        )
        username_query = (
            db.select(Username)
            .outerjoin(User)
            .options(joinedload(Username.user))
            .order_by(func.lower(Username._username), Username.id)
        )
        if username_filter is not None:
            username_count_query = username_count_query.where(username_filter)
            username_query = username_query.where(username_filter)

        username_count = db.session.scalar(username_count_query) or 0
        total_pages = max(
            1, (username_count + ADMIN_USERNAMES_PER_PAGE - 1) // ADMIN_USERNAMES_PER_PAGE
        )
        current_page = min(current_page, total_pages)
        page_offset = (current_page - 1) * ADMIN_USERNAMES_PER_PAGE
        all_usernames = list(
            db.session.scalars(
                username_query.limit(ADMIN_USERNAMES_PER_PAGE).offset(page_offset)
            ).all()
        )
        user_ids = {username.user_id for username in all_usernames}
        stripe_invoice_counts_by_user_id = stripe_invoice_counts_by_user_ids(user_ids)
        deletion_blocking_stripe_invoice_counts_by_user_id = (
            deletion_blocking_stripe_invoice_counts_by_user_ids(user_ids)
        )
        deletion_blocking_stripe_invoice_event_counts_by_user_id = (
            deletion_blocking_stripe_invoice_event_counts_by_user_ids(user_ids)
        )
        deletion_blocking_stripe_subscription_event_counts_by_user_id = (
            deletion_blocking_stripe_subscription_event_counts_by_user_ids(user_ids)
        )

        page_start = page_offset + 1 if username_count else 0
        page_end = min(page_offset + len(all_usernames), username_count)

        return render_template(
            "settings/admin.html",
            user=user,
            all_usernames=all_usernames,
            user_verification_enabled=current_app.config.get("USER_VERIFICATION_ENABLED"),
            account_category_choices=AccountCategory.choices(),
            admin_search_query=search_query,
            admin_current_page=current_page,
            admin_per_page=ADMIN_USERNAMES_PER_PAGE,
            admin_total_usernames=username_count,
            admin_total_pages=total_pages,
            admin_page_start=page_start,
            admin_page_end=page_end,
            stripe_invoice_counts_by_user_id=stripe_invoice_counts_by_user_id,
            deletion_blocking_stripe_invoice_counts_by_user_id=(
                deletion_blocking_stripe_invoice_counts_by_user_id
            ),
            deletion_blocking_stripe_invoice_event_counts_by_user_id=(
                deletion_blocking_stripe_invoice_event_counts_by_user_id
            ),
            deletion_blocking_stripe_subscription_event_counts_by_user_id=(
                deletion_blocking_stripe_subscription_event_counts_by_user_id
            ),
            csrf_token=generate_csrf(),
        )
