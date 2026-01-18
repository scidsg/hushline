from flask import (
    Flask,
    render_template,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.model import OrganizationSetting
from hushline.routes.common import get_directory_usernames


def register_directory_routes(app: Flask) -> None:
    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        usernames = list(get_directory_usernames())
        pgp_usernames = [username for username in usernames if username.user.pgp_key]
        info_usernames = [username for username in usernames if not username.user.pgp_key]
        verified_pgp_usernames = [username for username in pgp_usernames if username.is_verified]
        verified_info_usernames = [username for username in info_usernames if username.is_verified]
        return render_template(
            "directory.html",
            intro_text=OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO_TEXT),
            pgp_usernames=pgp_usernames,
            info_usernames=info_usernames,
            verified_pgp_usernames=verified_pgp_usernames,
            verified_info_usernames=verified_info_usernames,
            logged_in=logged_in,
        )

    @app.route("/directory/get-session-user.json")
    def session_user() -> dict[str, bool]:
        logged_in = "user_id" in session
        return {"logged_in": logged_in}

    @app.route("/directory/users.json")
    def directory_users() -> list[dict[str, str | bool | None]]:
        return [
            {
                "primary_username": username.username,
                "display_name": username.display_name or username.username,
                "bio": username.bio,
                "is_admin": username.user.is_admin,
                "is_verified": username.is_verified,
            }
            for username in get_directory_usernames()
        ]
