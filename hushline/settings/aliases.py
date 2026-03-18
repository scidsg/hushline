from typing import Tuple

from flask import (
    Blueprint,
    abort,
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
    FieldDefinition,
    FieldValue,
    Message,
    User,
    Username,
)
from hushline.settings.common import (
    build_field_forms,
    create_profile_forms,
    form_error,
    handle_field_post,
    handle_new_alias_form,
    handle_profile_post,
)
from hushline.settings.forms import (
    DeleteAliasForm,
    DirectoryVisibilityForm,
    DisplayNameForm,
    FieldForm,
    NewAliasForm,
    ProfileForm,
)

ProfileForms = tuple[DisplayNameForm, DirectoryVisibilityForm, ProfileForm]


def _render_alias_page(
    alias: Username,
    status_code: int = 200,
    forms: ProfileForms | None = None,
    submitted_field_form: FieldForm | None = None,
) -> tuple[str, int]:
    if forms is None:
        forms = create_profile_forms(alias)
    display_name_form, directory_visibility_form, profile_form = forms
    field_forms, new_field_form = build_field_forms(alias, submitted_form=submitted_field_form)

    return (
        render_template(
            "settings/alias.html",
            user=alias.user,
            alias=alias,
            display_name_form=display_name_form,
            directory_visibility_form=directory_visibility_form,
            profile_form=profile_form,
            field_forms=field_forms,
            new_field_form=new_field_form,
            delete_alias_form=DeleteAliasForm(),
        ),
        status_code,
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
    async def alias(username_id: int) -> Response | Tuple[str, int]:
        alias = db.session.scalars(
            db.select(Username).filter_by(
                id=username_id, user_id=session["user_id"], is_primary=False
            )
        ).one_or_none()
        if not alias:
            flash("⛔️ Alias not found.")
            return abort(404)

        status_code = 200
        if request.method == "POST":
            profile_forms = create_profile_forms(alias)
            delete_alias_form = DeleteAliasForm()
            if (
                delete_alias_form.submit.name in request.form
                and delete_alias_form.validate_on_submit()
            ):
                return delete_alias(alias.id)
            res = await handle_profile_post(*profile_forms, alias)
            if res:
                return res

            return _render_alias_page(
                alias,
                status_code=400,
                forms=profile_forms,
            )

        return _render_alias_page(alias, status_code=status_code)

    @bp.route("/alias/<int:username_id>/delete", methods=["POST"])
    @authentication_required
    def delete_alias(username_id: int) -> Response:
        delete_alias_form = DeleteAliasForm()
        if (
            delete_alias_form.submit.name not in request.form
            or not delete_alias_form.validate_on_submit()
        ):
            return abort(400)

        alias = db.session.scalars(
            db.select(Username).filter_by(
                id=username_id, user_id=session["user_id"], is_primary=False
            )
        ).one_or_none()
        if not alias:
            flash("⛔️ Alias not found.")
            return abort(404)

        with db.session.begin_nested():
            db.session.execute(
                db.delete(FieldValue).where(
                    FieldValue.field_definition_id.in_(
                        db.select(FieldDefinition.id).where(FieldDefinition.username_id == alias.id)
                    )
                )
            )
            db.session.execute(
                db.delete(FieldDefinition).where(FieldDefinition.username_id == alias.id)
            )
            db.session.execute(db.delete(Message).where(Message.username_id == alias.id))
            db.session.delete(alias)
            db.session.commit()

        flash("🗑️ Alias deleted successfully.")
        return redirect(url_for(".aliases"))

    @bp.route("/alias/<int:username_id>/fields", methods=["GET", "POST"])
    @authentication_required
    def alias_fields(username_id: int) -> Response | Tuple[str, int]:
        alias = db.session.scalars(
            db.select(Username).filter_by(
                id=username_id, user_id=session["user_id"], is_primary=False
            )
        ).one_or_none()
        if not alias:
            flash("⛔️ Alias not found.")
            return redirect(url_for(".aliases"))

        if not alias.user.fields_enabled:
            return abort(401)

        alias.create_default_field_defs()

        if request.method == "POST":
            field_form = FieldForm()
            res = handle_field_post(alias, field_form)
            if res:
                return res
            form_error()
            return _render_alias_page(
                alias,
                status_code=400,
                submitted_field_form=field_form,
            )

        return redirect(url_for(".alias", username_id=alias.id))
