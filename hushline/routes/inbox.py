from flask import (
    Flask,
    abort,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import (
    Message,
    MessageStatus,
    User,
    Username,
)


def register_inbox_routes(app: Flask) -> None:
    @app.route("/inbox")
    @authentication_required
    def inbox() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:  # silence, mypy
            abort(404)

        user_alias_count = db.session.scalar(
            db.select(db.func.count(Username.id).filter(Username.user_id == user.id))
        )

        status_filter = None
        if status_str := request.args.get("status"):
            try:
                status_filter = MessageStatus.parse_str(status_str)
            except ValueError:
                abort(400)

        query = (
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == user.id)
            .order_by(Message.created_at.desc())
        )
        if status_filter:
            query = query.filter(Message.status == status_filter)

        messages = list(db.session.scalars(query))
        return render_template(
            "inbox.html",
            user=user,
            messages=messages,
            status_filter=status_filter,
            message_statuses=list(MessageStatus),
            user_has_aliases=user_alias_count > 1,
        )
