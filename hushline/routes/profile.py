import secrets

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.crypto import decrypt_field
from hushline.db import db
from hushline.model import (
    OrganizationSetting,
    Username,
)
from hushline.routes.forms import MessageForm
from hushline.safe_template import safe_render_template


def register_profile_routes(app: Flask) -> None:
    @app.route("/to/<username>")
    def profile(username: str) -> Response | str:
        form = MessageForm()
        uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one_or_none()
        if not uname:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        # If the encrypted message is stored in the session, use it to populate the form
        scope = "submit_message"
        if (
            f"{scope}:salt" in session
            and f"{scope}:contact_method" in session
            and f"{scope}:content" in session
        ):
            try:
                form.contact_method.data = decrypt_field(
                    session[f"{scope}:contact_method"], scope, session[f"{scope}:salt"]
                )
                form.content.data = decrypt_field(
                    session[f"{scope}:content"], scope, session[f"{scope}:salt"]
                )
            except Exception:
                app.logger.error("Error decrypting content", exc_info=True)

            session.pop(f"{scope}:contact_method", None)
            session.pop(f"{scope}:content", None)
            session.pop(f"{scope}:salt", None)

        # Generate a simple math problem using secrets module (e.g., "What is 6 + 7?")
        num1 = secrets.randbelow(10) + 1
        num2 = secrets.randbelow(10) + 1
        math_problem = f"{num1} + {num2} ="
        session["math_answer"] = str(num1 + num2)  # Store the answer in session as a string

        profile_header = safe_render_template(
            OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE),
            {
                "display_name_or_username": uname.display_name or uname.username,
                "display_name": uname.display_name,
                "username": uname.username,
            },
        )

        return render_template(
            "profile.html",
            profile_header=profile_header,
            form=form,
            user=uname.user,
            username=uname,
            display_name_or_username=uname.display_name or uname.username,
            current_user_id=session.get("user_id"),
            public_key=uname.user.pgp_key,
            math_problem=math_problem,
        )
