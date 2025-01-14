from typing import Tuple

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

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import (
    User,
    Username,
)
from hushline.settings.common import (
    form_error,
    handle_display_name_form,
    handle_new_alias_form,
    handle_update_bio,
    handle_update_directory_visibility,
)
from hushline.settings.forms import (
    DirectoryVisibilityForm,
    DisplayNameForm,
    NewAliasForm,
    ProfileForm,
)


def register_aliases_routes(bp: Blueprint) -> None:
    @bp.route("/aliases", methods=["GET", "POST"])
    @authentication_required
    def aliases() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        new_alias_form = NewAliasForm()

        status_code = 200
        if request.method == "POST":
            if new_alias_form.validate() and (resp := handle_new_alias_form(user, new_alias_form)):
                return resp
            else:
                form_error()
                status_code = 400

        aliases = db.session.scalars(
            db.select(Username)
            .filter_by(is_primary=False, user_id=user.id)
            .order_by(db.func.coalesce(Username._display_name, Username._username))
        ).all()

        return render_template(
            "settings/aliases.html",
            user=user,
            aliases=aliases,
            new_alias_form=new_alias_form,
        ), status_code

    @bp.route("/alias/<int:username_id>", methods=["GET", "POST"])
    @authentication_required
    async def alias(username_id: int) -> Response | str:
        alias = db.session.scalars(
            db.select(Username).filter_by(
                id=username_id, user_id=session["user_id"], is_primary=False
            )
        ).one_or_none()
        if not alias:
            flash("Alias not found.")
            return redirect(url_for(".index"))

        display_name_form = DisplayNameForm()
        profile_form = ProfileForm()
        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=alias.show_in_directory
        )

        if request.method == "POST":
            if "update_bio" in request.form and profile_form.validate_on_submit():
                return await handle_update_bio(alias, profile_form)
            elif (
                "update_directory_visibility" in request.form
                and directory_visibility_form.validate_on_submit()
            ):
                return handle_update_directory_visibility(alias, directory_visibility_form)
            elif "update_display_name" in request.form and display_name_form.validate_on_submit():
                return handle_display_name_form(alias, display_name_form)
            else:
                current_app.logger.error(
                    f"Unable to handle form submission on endpoint {request.endpoint!r}, "
                    f"form fields: {request.form.keys()}"
                )
                flash("Uh oh. There was an error handling your data. Please notify the admin.")

        return render_template(
            "settings/alias.html",
            user=alias.user,
            alias=alias,
            display_name_form=display_name_form,
            directory_visibility_form=directory_visibility_form,
            profile_form=profile_form,
        )
