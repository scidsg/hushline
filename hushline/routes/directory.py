import unicodedata

from flask import (
    Flask,
    abort,
    render_template,
    session,
    url_for,
)
from unidecode import unidecode
from werkzeug.wrappers.response import Response

from hushline.model import (
    GlobaLeaksDirectoryListing,
    OrganizationSetting,
    PublicRecordListing,
    SecureDropDirectoryListing,
    Username,
    get_globaleaks_directory_listing,
    get_globaleaks_directory_listings,
    get_public_record_listing,
    get_public_record_listings,
    get_securedrop_directory_listing,
    get_securedrop_directory_listings,
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
        "is_globaleaks": False,
        "is_shodan": False,
        "is_securedrop": False,
        "is_automated": False,
        "message_capable": bool(username.user.pgp_key),
        "meta": f"@{username.username}",
        "location": None,
        "practice_tags": [],
        "source_label": None,
        "directory_section": None,
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
        "is_globaleaks": False,
        "is_shodan": False,
        "is_securedrop": False,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        "location": listing.location,
        "practice_tags": list(listing.practice_tags),
        "source_label": listing.source_label,
        "directory_section": listing.directory_section,
        "profile_url": url_for("public_record_listing", slug=listing.slug),
    }


def _globaleaks_row(listing: GlobaLeaksDirectoryListing) -> dict[str, object | None]:
    return {
        "entry_type": "globaleaks",
        "primary_username": None,
        "display_name": listing.name,
        "bio": listing.description,
        "is_admin": False,
        "is_verified": False,
        "has_pgp_key": False,
        "is_public_record": False,
        "is_globaleaks": True,
        "is_shodan": bool(getattr(listing, "is_shodan", False)),
        "is_securedrop": False,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        "location": listing.location,
        "practice_tags": [],
        "source_label": listing.source_label,
        "directory_section": listing.directory_section,
        "profile_url": url_for("globaleaks_listing", slug=listing.slug),
    }


def _securedrop_row(listing: SecureDropDirectoryListing) -> dict[str, object | None]:
    return {
        "entry_type": "securedrop",
        "primary_username": None,
        "display_name": listing.name,
        "bio": listing.description,
        "is_admin": False,
        "is_verified": False,
        "has_pgp_key": False,
        "is_public_record": False,
        "is_globaleaks": False,
        "is_shodan": False,
        "is_securedrop": True,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        "location": listing.location,
        "practice_tags": list(listing.topics),
        "source_label": listing.source_label,
        "directory_section": listing.directory_section,
        "profile_url": url_for("securedrop_listing", slug=listing.slug),
    }


def _all_directory_entry_sort_key(entry: dict[str, object | None]) -> tuple[str, str]:
    display_name = str(entry.get("display_name") or "")
    normalized_name = unicodedata.normalize("NFKC", display_name).strip()
    transliterated_name = unidecode(normalized_name).casefold()
    return transliterated_name, normalized_name.casefold()


def register_directory_routes(app: Flask) -> None:
    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        usernames = list(get_directory_usernames())
        all_public_record_listings = (
            list(get_public_record_listings())
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        public_record_listings = [
            listing
            for listing in all_public_record_listings
            if listing.directory_section != "legacy_public_record"
        ]
        legacy_public_record_listings = [
            listing
            for listing in all_public_record_listings
            if listing.directory_section == "legacy_public_record"
        ]
        globaleaks_listings = (
            list(get_globaleaks_directory_listings())
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        securedrop_listings = (
            list(get_securedrop_directory_listings())
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        pgp_usernames = [username for username in usernames if username.user.pgp_key]
        info_usernames = [username for username in usernames if not username.user.pgp_key]
        verified_pgp_usernames = [username for username in pgp_usernames if username.is_verified]
        verified_info_usernames = [username for username in info_usernames if username.is_verified]
        all_directory_entries = [
            *[_directory_user_row(username) for username in usernames],
            *[_public_record_row(listing) for listing in all_public_record_listings],
            *[_globaleaks_row(listing) for listing in globaleaks_listings],
            *[_securedrop_row(listing) for listing in securedrop_listings],
        ]
        all_directory_entries.sort(key=_all_directory_entry_sort_key)
        return render_template(
            "directory.html",
            intro_text=OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO_TEXT),
            pgp_usernames=pgp_usernames,
            info_usernames=info_usernames,
            verified_pgp_usernames=verified_pgp_usernames,
            verified_info_usernames=verified_info_usernames,
            public_record_all_listings=all_public_record_listings,
            public_record_listings=public_record_listings,
            legacy_public_record_listings=legacy_public_record_listings,
            public_record_total_count=len(all_public_record_listings),
            globaleaks_listings=globaleaks_listings,
            globaleaks_total_count=len(globaleaks_listings),
            securedrop_listings=securedrop_listings,
            securedrop_total_count=len(securedrop_listings),
            all_directory_entries=all_directory_entries,
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

    @app.route("/directory/globaleaks/<slug>")
    def globaleaks_listing(slug: str) -> Response | str:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            abort(404)

        listing = get_globaleaks_directory_listing(slug)
        if listing is None:
            abort(404)

        return render_template("directory_globaleaks.html", listing=listing)

    @app.route("/directory/securedrop/<slug>")
    def securedrop_listing(slug: str) -> Response | str:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            abort(404)

        listing = get_securedrop_directory_listing(slug)
        if listing is None:
            abort(404)

        return render_template("directory_securedrop.html", listing=listing)

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
        globaleaks_rows = (
            [_globaleaks_row(listing) for listing in get_globaleaks_directory_listings()]
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        securedrop_rows = (
            [_securedrop_row(listing) for listing in get_securedrop_directory_listings()]
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        return [
            *[_directory_user_row(username) for username in get_directory_usernames()],
            *public_record_rows,
            *globaleaks_rows,
            *securedrop_rows,
        ]
