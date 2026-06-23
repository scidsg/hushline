from flask import (
    Blueprint,
    render_template,
    session,
)
from sqlalchemy import distinct, func

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import ChatKey, User


def _percentage(count: int, total: int) -> float:
    return (count / total * 100) if total else 0


def register_metrics_routes(bp: Blueprint) -> None:
    @bp.route("/metrics")
    @admin_authentication_required
    def metrics() -> str:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        user_count = db.session.scalar(db.select(func.count(User.id))) or 0
        two_fa_count = (
            db.session.scalar(db.select(func.count(User.id)).where(User._totp_secret.is_not(None)))
            or 0
        )
        pgp_key_count = (
            db.session.scalar(db.select(func.count(User.id)).where(User._pgp_key.is_not(None))) or 0
        )
        chat_key_count = (
            db.session.scalar(
                db.select(func.count(distinct(ChatKey.user_id))).where(
                    ChatKey.disabled_at.is_(None)
                )
            )
            or 0
        )

        return render_template(
            "settings/metrics.html",
            user=user,
            user_count=user_count,
            two_fa_count=two_fa_count,
            pgp_key_count=pgp_key_count,
            chat_key_count=chat_key_count,
            two_fa_percentage=_percentage(two_fa_count, user_count),
            pgp_key_percentage=_percentage(pgp_key_count, user_count),
            chat_key_percentage=_percentage(chat_key_count, user_count),
        )
