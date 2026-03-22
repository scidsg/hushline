import unicodedata
from typing import cast

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
    AccountCategory,
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
from hushline.model.directory_listing_geography import (
    DirectoryListingGeography,
    build_directory_geography,
)
from hushline.routes.common import get_directory_usernames

_LEGACY_COUNTRY_NAME_BY_CODE = {
    "AU": "Australia",
    "AT": "Austria",
    "BE": "Belgium",
    "FI": "Finland",
    "FR": "France",
    "DE": "Germany",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "LU": "Luxembourg",
    "NL": "Netherlands",
    "PT": "Portugal",
    "SG": "Singapore",
    "ES": "Spain",
    "SE": "Sweden",
    "US": "United States",
}


def _normalized_filter_value(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _normalized_attorney_filter_country(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    legacy_country = _LEGACY_COUNTRY_NAME_BY_CODE.get(normalized.upper())
    if legacy_country is not None:
        return legacy_country

    return build_directory_geography(country=normalized).country


def _attorney_filter_state(attorney_filter_metadata: dict[str, object]) -> dict[str, str | None]:
    country = _normalized_attorney_filter_country(request.args.get("country"))
    region_code = _normalized_filter_value(request.args.get("region"))
    subdivision = None
    raw_regions = cast(
        dict[str, list[dict[str, str]]], attorney_filter_metadata.get("regions") or {}
    )
    raw_countries = cast(list[dict[str, str]], attorney_filter_metadata.get("countries") or [])
    regions_by_country = {
        country_name: {str(region["code"]): str(region["label"]) for region in country_regions}
        for country_name, country_regions in raw_regions.items()
    }
    available_countries = {str(country_option["code"]) for country_option in raw_countries}
    available_countries_by_casefold = {
        available_country.casefold(): available_country for available_country in available_countries
    }

    if country is not None:
        country = available_countries_by_casefold.get(country.casefold())

    if region_code:
        if country:
            country_regions = regions_by_country.get(country, {})
            region_codes_by_casefold = {code.casefold(): code for code in country_regions}
            region_code = region_codes_by_casefold.get(region_code.casefold())
            if region_code is not None:
                subdivision = country_regions.get(region_code)
        else:
            for inferred_country, region_names in regions_by_country.items():
                region_codes_by_casefold = {code.casefold(): code for code in region_names}
                matched_region_code = region_codes_by_casefold.get(region_code.casefold())
                if matched_region_code is not None:
                    country = inferred_country
                    region_code = matched_region_code
                    subdivision = region_names[matched_region_code]
                    break

        if subdivision is None:
            region_code = None

    return {
        "country": country,
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


def _username_matches_attorney_filters(
    username: Username, filter_state: dict[str, str | None]
) -> bool:
    geography = _username_geography(username)

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
    attorney_usernames: list[Username] | tuple[Username, ...] = (),
) -> dict[str, object]:
    countries: dict[str, int] = {}
    regions: dict[str, dict[str, dict[str, object]]] = {}

    def add_geography(geography: DirectoryListingGeography) -> None:
        country = geography.country
        subdivision = geography.subdivision
        subdivision_code = geography.subdivision_code

        if country is None:
            return

        countries[country] = countries.get(country, 0) + 1

        if subdivision is None or subdivision_code is None:
            return

        country_regions = regions.setdefault(country, {})
        region_entry = cast(
            dict[str, object],
            country_regions.setdefault(
                subdivision_code,
                {"label": subdivision, "count": 0},
            ),
        )
        region_entry["count"] = cast(int, region_entry["count"]) + 1

    for listing in listings:
        add_geography(listing.geography)

    for username in attorney_usernames:
        add_geography(_username_geography(username))

    return {
        "countries": [
            {"code": country, "label": country, "count": countries[country]}
            for country in sorted(countries, key=str.casefold)
        ],
        "regions": {
            country_name: [
                {
                    "code": code,
                    "label": str(region_data["label"]),
                    "count": cast(int, region_data["count"]),
                }
                for code, region_data in sorted(
                    country_regions.items(), key=lambda item: str(item[1]["label"]).casefold()
                )
            ]
            for country_name, country_regions in sorted(regions.items())
        },
    }


def _geography_fields(
    city: str | None,
    country: str | None,
    subdivision: str | None,
    subdivision_code: str | None,
    countries: tuple[str, ...] | list[str],
) -> dict[str, object | None]:
    return {
        "city": city,
        "country": country,
        "subdivision": subdivision,
        "subdivision_code": subdivision_code,
        "countries": list(countries),
    }


def _username_geography(username: Username) -> DirectoryListingGeography:
    user = username.user
    return build_directory_geography(
        city=getattr(user, "city", None),
        country=getattr(user, "country", None),
        subdivision=getattr(user, "subdivision", None),
    )


def _is_self_reported_attorney(username: Username) -> bool:
    return getattr(username.user, "account_category", None) == AccountCategory.LAWYER.value


def _directory_user_row(username: Username) -> dict[str, object | None]:
    user = username.user
    geography = _username_geography(username)
    return {
        "entry_type": "user",
        "primary_username": username.username,
        "display_name": username.display_name or username.username,
        "bio": username.bio,
        "account_category": getattr(user, "account_category", None),
        "account_category_label": getattr(user, "account_category_label", None),
        "is_admin": user.is_admin,
        "is_verified": username.is_verified,
        "has_pgp_key": bool(user.pgp_key),
        "is_public_record": False,
        "is_globaleaks": False,
        "is_securedrop": False,
        "is_automated": False,
        "message_capable": bool(user.pgp_key),
        "meta": f"@{username.username}",
        **_geography_fields(
            geography.city,
            geography.country,
            geography.subdivision,
            geography.subdivision_code,
            geography.countries,
        ),
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
        "account_category": None,
        "account_category_label": None,
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
            geography.subdivision_code,
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
        "account_category": None,
        "account_category_label": None,
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
            geography.subdivision_code,
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
        "account_category": None,
        "account_category_label": None,
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
            geography.subdivision_code,
            geography.countries,
        ),
        "practice_tags": list(listing.topics),
        "source_label": listing.source_label,
        "directory_section": listing.directory_section,
        "profile_url": url_for("securedrop_listing", slug=listing.slug),
    }


def _all_directory_entry_identity(entry: dict[str, object | None]) -> str:
    return str(entry.get("display_name") or entry.get("primary_username") or "")


def _all_directory_entry_sort_key(entry: dict[str, object | None]) -> tuple[bool, str, str]:
    is_admin = bool(entry.get("is_admin"))
    sort_identity = _all_directory_entry_identity(entry)
    normalized_identity = unicodedata.normalize("NFKC", sort_identity).strip()
    transliterated_identity = unidecode(normalized_identity).casefold()
    return not is_admin, transliterated_identity, normalized_identity.casefold()


def _all_directory_entry_client_sort_fields(
    entry: dict[str, object | None],
) -> dict[str, str]:
    _, transliterated_identity, normalized_identity = _all_directory_entry_sort_key(entry)
    return {
        "all_tab_sort_transliterated": transliterated_identity,
        "all_tab_sort_normalized": normalized_identity,
    }


def register_directory_routes(app: Flask) -> None:
    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        usernames = list(get_directory_usernames())
        attorney_usernames = [
            username for username in usernames if _is_self_reported_attorney(username)
        ]
        all_public_record_listings = (
            list(get_public_record_listings())
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        attorney_filter_metadata = _attorney_filter_metadata(
            all_public_record_listings, attorney_usernames
        )
        attorney_filter_state = _attorney_filter_state(attorney_filter_metadata)
        filtered_attorney_usernames = [
            username
            for username in attorney_usernames
            if _username_matches_attorney_filters(username, attorney_filter_state)
        ]
        filtered_public_record_listings = _filter_public_record_listings(
            all_public_record_listings, attorney_filter_state
        )
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
            attorney_usernames=filtered_attorney_usernames,
            public_record_all_listings=filtered_public_record_listings,
            public_record_listings=public_record_listings,
            legacy_public_record_listings=legacy_public_record_listings,
            public_record_total_count=len(filtered_attorney_usernames)
            + len(filtered_public_record_listings),
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

        return _attorney_filter_metadata(
            get_public_record_listings(),
            tuple(
                username
                for username in get_directory_usernames()
                if _is_self_reported_attorney(username)
            ),
        )

    @app.route("/directory/users.json")
    def directory_users() -> list[dict[str, object | None]]:
        public_record_listings = (
            list(get_public_record_listings())
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        attorney_filter_state = _attorney_filter_state(
            _attorney_filter_metadata(
                public_record_listings,
                tuple(
                    username
                    for username in get_directory_usernames()
                    if _is_self_reported_attorney(username)
                ),
            )
        )
        public_record_rows = (
            [
                _public_record_row(listing)
                for listing in _filter_public_record_listings(
                    public_record_listings, attorney_filter_state
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
            {
                **entry,
                **_all_directory_entry_client_sort_fields(entry),
            }
            for entry in [
                *[_directory_user_row(username) for username in get_directory_usernames()],
                *public_record_rows,
                *globaleaks_rows,
                *securedrop_rows,
            ]
        ]
