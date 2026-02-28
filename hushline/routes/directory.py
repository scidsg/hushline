from flask import (
    Flask,
    abort,
    render_template,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.model import (
    OrganizationSetting,
    PublicRecordListing,
    Username,
    get_public_record_listing,
    get_public_record_listings,
)
from hushline.routes.common import get_directory_usernames


def _directory_user_row(username: Username) -> dict[str, object | None]:
    return {
        "entry_type": "user",
        "primary_username": username.username,
        "display_name": username.display_name or username.username,
        "bio": username.bio,
        "is_admin": username.user.is_admin,
        "is_verified": username.is_verified,
        "has_pgp_key": bool(username.user.pgp_key),
        "is_public_record": False,
        "is_automated": False,
        "message_capable": bool(username.user.pgp_key),
        "meta": f"@{username.username}",
        "location": None,
        "practice_tags": [],
        "source_label": None,
        "profile_url": url_for("profile", username=username.username),
    }


def _public_record_row(listing: PublicRecordListing) -> dict[str, object | None]:
    return {
        "entry_type": "public_record",
        "primary_username": None,
        "display_name": listing.name,
        "bio": listing.description,
        "is_admin": False,
        "is_verified": False,
        "has_pgp_key": False,
        "is_public_record": True,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        "location": listing.location,
        "practice_tags": list(listing.practice_tags),
        "source_label": listing.source_label,
        "profile_url": url_for("public_record_listing", slug=listing.slug),
    }


def register_directory_routes(app: Flask) -> None:
    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        usernames = list(get_directory_usernames())
        public_record_listings = (
            list(get_public_record_listings()) if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"] else []
        )
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
            public_record_listings=public_record_listings,
            logged_in=logged_in,
        )

    @app.route("/directory/public-records/<slug>")
    def public_record_listing(slug: str) -> Response | str:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            abort(404)

        listing = get_public_record_listing(slug)
        if listing is None:
            abort(404)

        return render_template("directory_public_record.html", listing=listing)

    @app.route("/directory/get-session-user.json")
    def session_user() -> dict[str, bool]:
        logged_in = "user_id" in session
        return {"logged_in": logged_in}

    @app.route("/directory/users.json")
    def directory_users() -> list[dict[str, object | None]]:
        public_record_rows = (
            [_public_record_row(listing) for listing in get_public_record_listings()]
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        return [
            *[_directory_user_row(username) for username in get_directory_usernames()],
            *public_record_rows,
        ]
