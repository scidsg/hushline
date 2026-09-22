from uuid import uuid4

from flask import (
    Flask,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from flask_wtf.csrf import validate_csrf
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import authentication_required, get_session_user
from hushline.chat_key_lifecycle import chat_key_fingerprint
from hushline.db import db
from hushline.model import Conversation, ConversationParticipant, OrganizationSetting


def register_case_builder_routes(app: Flask) -> None:
    @app.get("/case-builder")
    def case_builder() -> Response:
        brand_name = OrganizationSetting.fetch_one(OrganizationSetting.BRAND_NAME) or "Hush Line"
        # Avoid the shared context processors: they read account and session state that this
        # account-independent workspace does not need.
        template = current_app.jinja_env.get_template("case_builder.html")
        response = make_response(
            template.render(
                brand_name=brand_name,
                case_builder_script_url=url_for(
                    "static", filename="js/case-builder.js", v="case-builder-5"
                ),
                stylesheet_url=url_for("static", filename="css/style.css", v="case-builder-5"),
                leave_url=url_for("directory"),
                counsel_url=url_for("directory"),
                chat_url=url_for("inbox"),
                tip_url=url_for("directory"),
                self_url=url_for("case_builder_self"),
            )
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/case-builder/self")
    def case_builder_self() -> Response:
        user = get_session_user() if session.get("is_authenticated") else None
        if user is None:
            session["case_builder_import_id"] = str(uuid4())
            return redirect(url_for("register", next=url_for("case_builder_import")))
        return redirect(url_for("profile", username=user.primary_username.username))

    @app.route("/case-builder/import", methods=["GET", "POST"])
    @authentication_required
    def case_builder_import() -> Response:
        user = get_session_user()
        if user is None or user.is_suspended:
            abort(403)
        import_id = session.setdefault("case_builder_import_id", str(uuid4()))
        if request.method == "GET":
            response = make_response(render_template("case_builder_import.html", form=FlaskForm()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
            return response
        try:
            validate_csrf(request.headers.get("X-CSRFToken"))
        except ValidationError:
            abort(400)
        if request.get_json(silent=True) != {}:
            abort(400)
        key = user.active_chat_key
        if key is None or not key.public_key or not key.public_signing_key:
            abort(409)
        thread = db.session.scalar(
            db.select(Conversation).where(Conversation.public_id == import_id)
        )
        if thread is None:
            thread = Conversation()
            thread.public_id = import_id
            participant = ConversationParticipant()
            participant.user = user
            participant.has_usable_public_key = True
            thread.participants.append(participant)
            db.session.add(thread)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                thread = db.session.scalar(
                    db.select(Conversation).where(Conversation.public_id == import_id)
                )
        if thread is None or len(thread.participants) != 1:
            abort(403)
        participant = thread.participant_for_user_id(user.id)
        if participant is None or participant.deleted_at is not None:
            abort(403)
        response = jsonify(
            saved=bool(thread.messages),
            inbox_url=url_for("inbox"),
            message_url=url_for("append_conversation_message", public_id=thread.public_id),
            conversation_public_id=thread.public_id,
            participant_key={
                "participant_id": participant.id,
                "key_version": key.key_version,
                "public_key": key.public_key,
                "public_key_fingerprint": chat_key_fingerprint(key.public_key),
                "public_signing_key": key.public_signing_key,
            },
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
