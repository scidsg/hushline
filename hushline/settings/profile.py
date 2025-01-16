from typing import Tuple

from flask import (
    Blueprint,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import (
    Tier,
    User,
)
from hushline.settings.common import (
    form_error,
    handle_display_name_form,
    handle_update_bio,
    handle_update_directory_visibility,
)
from hushline.settings.forms import (
    DirectoryVisibilityForm,
    DisplayNameForm,
    ProfileForm,
)


def register_profile_routes(bp: Blueprint) -> None:
    @bp.route("/profile", methods=["GET", "POST"])
    @authentication_required
    async def profile() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        username = user.primary_username

        if username is None:
            raise Exception("Username was unexpectedly none")

        display_name_form = DisplayNameForm(display_name=username.display_name)
        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=username.show_in_directory
        )
        profile_form = ProfileForm(
            bio=username.bio or "",
            **{
                f"extra_field_label{i}": getattr(username, f"extra_field_label{i}", "")
                for i in range(1, 5)
            },
            **{
                f"extra_field_value{i}": getattr(username, f"extra_field_value{i}", "")
                for i in range(1, 5)
            },
        )

        status_code = 200
        if request.method == "POST":
            if display_name_form.submit.name in request.form and display_name_form.validate():
                return handle_display_name_form(username, display_name_form)
            elif (
                directory_visibility_form.submit.name in request.form
                and directory_visibility_form.validate()
            ):
                return handle_update_directory_visibility(username, directory_visibility_form)
            elif profile_form.submit.name in request.form and profile_form.validate():
                return await handle_update_bio(username, profile_form)
            else:
                form_error()
                status_code = 400

        business_tier = Tier.business_tier()
        business_tier_display_price = ""
        if business_tier:
            price_usd = business_tier.monthly_amount / 100
            if price_usd % 1 == 0:
                business_tier_display_price = str(int(price_usd))
            else:
                business_tier_display_price = f"{price_usd:.2f}"

        return render_template(
            "settings/profile.html",
            user=user,
            username=username,
            display_name_form=display_name_form,
            directory_visibility_form=directory_visibility_form,
            profile_form=profile_form,
            business_tier_display_price=business_tier_display_price,
        ), status_code
