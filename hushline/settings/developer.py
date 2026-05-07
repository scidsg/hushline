from typing import Tuple

from flask import (
    Blueprint,
    abort,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.embeds import embed_iframe_snippet
from hushline.model import OrganizationSetting, User, Username
from hushline.settings.common import (
    create_embed_settings_form,
    handle_embed_settings_form,
)
from hushline.settings.forms import EmbedSettingsForm


def _render_developer_page(
    user: User,
    username: Username,
    status_code: int = 200,
    embed_settings_form: EmbedSettingsForm | None = None,
) -> tuple[str, int]:
    if embed_settings_form is None:
        embed_settings_form = create_embed_settings_form(username)

    return (
        render_template(
            "settings/developer.html",
            user=user,
            username=username,
            is_alias=False,
            embed_settings_action=url_for(".developer"),
            embed_settings_form=embed_settings_form,
            embeddable_forms_enabled=bool(
                OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED)
            ),
            embed_iframe_snippet=(
                embed_iframe_snippet(username) if username.embed_is_eligible else ""
            ),
        ),
        status_code,
    )


def register_developer_routes(bp: Blueprint) -> None:
    @bp.route("/developer", methods=["GET", "POST"])
    @authentication_required
    def developer() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        if not user.is_current_paid_super_user:
            return abort(401)

        username = user.primary_username
        if username is None:
            raise Exception("Username was unexpectedly none")

        if request.method == "POST":
            embed_settings_form = create_embed_settings_form(username, submitted=True)
            res = handle_embed_settings_form(username, embed_settings_form)
            if res:
                return res
            return _render_developer_page(
                user,
                username,
                status_code=400,
                embed_settings_form=embed_settings_form,
            )

        return _render_developer_page(user, username)
