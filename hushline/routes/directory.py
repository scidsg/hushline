import unicodedata

from flask import (
    Flask,
    abort,
    render_template,
    request,
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
from hushline.model.directory_listing_geography import US_SUBDIVISION_NAMES
from hushline.routes.common import get_directory_usernames

_COUNTRY_CODE_BY_NAME = {
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "India": "IN",
    "Italy": "IT",
    "Japan": "JP",
    "Luxembourg": "LU",
    "Netherlands": "NL",
    "Portugal": "PT",
    "Singapore": "SG",
    "Spain": "ES",
    "Sweden": "SE",
    "United States": "US",
}
_COUNTRY_NAME_BY_CODE = {code: name for name, code in _COUNTRY_CODE_BY_NAME.items()}
_REGION_NAMES_BY_COUNTRY_CODE = {"US": US_SUBDIVISION_NAMES}
_REGION_CODES_BY_COUNTRY_NAME = {
    _COUNTRY_NAME_BY_CODE[country_code]: {
        region_name: region_code for region_code, region_name in region_names.items()
    }
    for country_code, region_names in _REGION_NAMES_BY_COUNTRY_CODE.items()
}


def _normalized_filter_code(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().upper()
    return normalized or None


def _attorney_filter_state() -> dict[str, str | None]:
    country_code = _normalized_filter_code(request.args.get("country"))
    region_code = _normalized_filter_code(request.args.get("region"))

    country = _COUNTRY_NAME_BY_CODE.get(country_code) if country_code else None
    subdivision = None

    if region_code:
        if country_code:
            subdivision = _REGION_NAMES_BY_COUNTRY_CODE.get(country_code, {}).get(region_code)
        else:
            for inferred_country_code, region_names in _REGION_NAMES_BY_COUNTRY_CODE.items():
                if region_code in region_names:
                    country_code = inferred_country_code
                    country = _COUNTRY_NAME_BY_CODE[inferred_country_code]
                    subdivision = region_names[region_code]
                    break

        if subdivision is None:
            region_code = None

    if country is None:
        country_code = None

    return {
        "country": country,
        "country_code": country_code,
        "region": subdivision,
        "region_code": region_code,
    }


def _listing_matches_attorney_filters(
    listing: PublicRecordListing, filter_state: dict[str, str | None]
) -> bool:
    geography = listing.geography

    if filter_state["country"] and geography.country != filter_state["country"]:
        return False

    if filter_state["region"] and geography.subdivision != filter_state["region"]:
        return False

    return True


def _filter_public_record_listings(
    listings: list[PublicRecordListing] | tuple[PublicRecordListing, ...],
    filter_state: dict[str, str | None],
) -> list[PublicRecordListing]:
    return [
        listing for listing in listings if _listing_matches_attorney_filters(listing, filter_state)
    ]


def _attorney_filter_metadata(
    listings: list[PublicRecordListing] | tuple[PublicRecordListing, ...],
) -> dict[str, object]:
    countries: dict[str, str] = {}
    regions: dict[str, dict[str, str]] = {}

    for listing in listings:
        geography = listing.geography
        if geography.country is None:
            continue

        country_code = _COUNTRY_CODE_BY_NAME.get(geography.country)
        if country_code is None:
            continue

        countries[country_code] = geography.country

        if geography.subdivision is None:
            continue

        region_code = _REGION_CODES_BY_COUNTRY_NAME.get(geography.country, {}).get(
            geography.subdivision
        )
        if region_code is None:
            continue

        regions.setdefault(country_code, {})[region_code] = geography.subdivision

    return {
        "countries": [
            {"code": code, "label": label}
            for code, label in sorted(countries.items(), key=lambda item: item[1].casefold())
        ],
        "regions": {
            country_code: [
                {"code": code, "label": label}
                for code, label in sorted(
                    country_regions.items(), key=lambda item: item[1].casefold()
                )
            ]
            for country_code, country_regions in sorted(regions.items())
        },
    }


def _geography_fields(
    city: str | None,
    country: str | None,
    subdivision: str | None,
    countries: tuple[str, ...] | list[str],
) -> dict[str, object | None]:
    return {
        "city": city,
        "country": country,
        "subdivision": subdivision,
        "countries": list(countries),
    }


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
        "is_securedrop": False,
        "is_automated": False,
        "message_capable": bool(username.user.pgp_key),
        "meta": f"@{username.username}",
        **_geography_fields(None, None, None, ()),
        "practice_tags": [],
        "source_label": None,
        "directory_section": None,
        "profile_url": url_for("profile", username=username.username),
    }


def _public_record_row(listing: PublicRecordListing) -> dict[str, object | None]:
    geography = listing.geography
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
        "is_securedrop": False,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        **_geography_fields(
            geography.city,
            geography.country,
            geography.subdivision,
            geography.countries,
        ),
        "practice_tags": list(listing.practice_tags),
        "source_label": listing.source_label,
        "directory_section": listing.directory_section,
        "profile_url": url_for("public_record_listing", slug=listing.slug),
    }


def _globaleaks_row(listing: GlobaLeaksDirectoryListing) -> dict[str, object | None]:
    geography = listing.geography
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
        "is_securedrop": False,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        **_geography_fields(
            geography.city,
            geography.country,
            geography.subdivision,
            geography.countries,
        ),
        "practice_tags": [],
        "source_label": listing.source_label,
        "directory_section": listing.directory_section,
        "profile_url": url_for("globaleaks_listing", slug=listing.slug),
    }


def _securedrop_row(listing: SecureDropDirectoryListing) -> dict[str, object | None]:
    geography = listing.geography
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
        "is_securedrop": True,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website,
        **_geography_fields(
            geography.city,
            geography.country,
            geography.subdivision,
            geography.countries,
        ),
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
        attorney_filter_state = _attorney_filter_state()
        all_public_record_listings = (
            list(get_public_record_listings())
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        filtered_public_record_listings = _filter_public_record_listings(
            all_public_record_listings, attorney_filter_state
        )
        attorney_filter_metadata = _attorney_filter_metadata(all_public_record_listings)
        public_record_listings = [
            listing
            for listing in filtered_public_record_listings
            if listing.directory_section != "legacy_public_record"
        ]
        legacy_public_record_listings = [
            listing
            for listing in filtered_public_record_listings
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
            *[_public_record_row(listing) for listing in filtered_public_record_listings],
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
            public_record_all_listings=filtered_public_record_listings,
            public_record_listings=public_record_listings,
            legacy_public_record_listings=legacy_public_record_listings,
            public_record_total_count=len(all_public_record_listings),
            attorney_filter_metadata=attorney_filter_metadata,
            attorney_filter_state=attorney_filter_state,
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

    @app.route("/directory/attorney-filters.json")
    def directory_attorney_filters() -> dict[str, object]:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            return {
                "countries": [],
                "regions": {},
            }

        return _attorney_filter_metadata(get_public_record_listings())

    @app.route("/directory/users.json")
    def directory_users() -> list[dict[str, object | None]]:
        attorney_filter_state = _attorney_filter_state()
        public_record_rows = (
            [
                _public_record_row(listing)
                for listing in _filter_public_record_listings(
                    get_public_record_listings(), attorney_filter_state
                )
            ]
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
