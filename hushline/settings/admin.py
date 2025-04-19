from flask import (
    Blueprint,
    current_app,
    render_template,
    session,
)

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import User, Username


def register_admin_routes(bp: Blueprint) -> None:
    @bp.route("/admin")
    @admin_authentication_required
    def admin() -> str:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        all_users = list(
            db.session.scalars(db.select(User).join(Username).order_by(Username._username)).all()
        )
        user_count = len(all_users)
        two_fa_count = sum(1 for _ in filter(lambda x: x._totp_secret, all_users))
        pgp_key_count = sum(1 for _ in filter(lambda x: x._pgp_key, all_users))

        return render_template(
            "settings/admin.html",
            user=user,
            all_users=all_users,
            user_count=user_count,
            two_fa_count=two_fa_count,
            pgp_key_count=pgp_key_count,
            two_fa_percentage=(two_fa_count / user_count * 100) if user_count else 0,
            pgp_key_percentage=(pgp_key_count / user_count * 100) if user_count else 0,
            is_managed_service=current_app.config.get("MANAGED_SERVICE"),
        )
