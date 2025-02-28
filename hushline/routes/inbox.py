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

        status_count_results = db.session.execute(
            db.select(Message.status, db.func.count())
            .join(Username)
            .filter(Username.user_id == user.id)
            .group_by(Message.status)
        ).all()
        status_counts_map = {x[0]: x[1] for x in status_count_results}
        message_statuses = [(x, status_counts_map.get(x, 0)) for x in MessageStatus]

        return render_template(
            "inbox.html",
            user=user,
            messages=messages,
            status_filter=status_filter,
            total_messages=sum(x[1] for x in message_statuses),
            message_statuses=message_statuses,
            user_has_aliases=user_alias_count > 1,
        )
