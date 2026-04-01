from typing import Tuple

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.geo import city_options_for_state, state_options
from hushline.model import (
    Tier,
    User,
    Username,
)
from hushline.settings.common import (
    build_field_forms,
    create_profile_forms,
    form_error,
    handle_field_post,
    handle_profile_post,
)
from hushline.settings.forms import (
    DirectoryVisibilityForm,
    DisplayNameForm,
    FieldForm,
    ProfileForm,
)

ProfileForms = tuple[DisplayNameForm, DirectoryVisibilityForm, ProfileForm]


def _business_tier_display_price() -> str:
    business_tier = Tier.business_tier()
    if not business_tier:
        return ""

    price_usd = business_tier.monthly_amount / 100
    if price_usd % 1 == 0:
        return str(int(price_usd))
    return f"{price_usd:.2f}"


def _render_profile_page(
    user: User,
    username: Username,
    status_code: int = 200,
    forms: ProfileForms | None = None,
    submitted_field_form: FieldForm | None = None,
) -> tuple[str, int]:
    if forms is None:
        forms = create_profile_forms(username)
    display_name_form, directory_visibility_form, profile_form = forms
    field_forms, new_field_form = build_field_forms(username, submitted_form=submitted_field_form)

    return (
        render_template(
            "settings/profile.html",
            user=user,
            username=username,
            display_name_form=display_name_form,
            directory_visibility_form=directory_visibility_form,
            profile_form=profile_form,
            field_forms=field_forms,
            new_field_form=new_field_form,
            business_tier_display_price=_business_tier_display_price(),
        ),
        status_code,
    )


def register_profile_routes(bp: Blueprint) -> None:
    @bp.route("/profile", methods=["GET", "POST"])
    @authentication_required
    async def profile() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        username = user.primary_username

        if username is None:
            raise Exception("Username was unexpectedly none")

        status_code = 200
        if request.method == "POST":
            profile_forms = create_profile_forms(username)
            res = await handle_profile_post(*profile_forms, username)
            if res:
                return res

            return _render_profile_page(
                user,
                username,
                status_code=400,
                forms=profile_forms,
            )

        return _render_profile_page(user, username, status_code=status_code)

    @bp.route("/profile/states.json")
    @authentication_required
    def profile_states() -> Response:
        return jsonify({"states": state_options(request.args.get("country"))})

    @bp.route("/profile/cities.json")
    @authentication_required
    def profile_cities() -> Response:
        return jsonify(
            {
                "cities": city_options_for_state(
                    request.args.get("country"),
                    request.args.get("subdivision"),
                )
            }
        )

    @bp.route("/profile/fields", methods=["GET", "POST"])
    @authentication_required
    def profile_fields() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        if not user.fields_enabled:
            return abort(401)

        username = user.primary_username

        if username is None:
            raise Exception("Username not found")

        username.create_default_field_defs()

        if request.method == "POST":
            field_form = FieldForm()
            res = handle_field_post(username, field_form)
            if res:
                return res
            form_error()
            return _render_profile_page(
                user,
                username,
                status_code=400,
                submitted_field_form=field_form,
            )

        return redirect(url_for(".profile"))
