import unicodedata
from typing import Sequence, cast
from urllib.parse import urlencode

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
    NewsroomDirectoryListing,
    OrganizationSetting,
    PublicRecordListing,
    SecureDropDirectoryListing,
    Username,
    get_globaleaks_directory_listing,
    get_globaleaks_directory_listings,
    get_newsroom_directory_listing,
    get_newsroom_directory_listings,
    get_public_record_listing,
    get_public_record_listings,
    get_securedrop_directory_listing,
    get_securedrop_directory_listings,
)
from hushline.model.directory_listing_geography import (
    DirectoryListingGeography,
    build_directory_geography,
)
from hushline.routes.common import get_directory_usernames, show_directory_caution_badge

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
_ALL_LISTING_TYPE_LABELS = (
    ("verified", "Verified"),
    ("attorneys", "Attorneys"),
    ("newsrooms", "Newsrooms"),
    ("securedrop", "SecureDrop"),
    ("globaleaks", "GlobaLeaks"),
)


def _normalized_filter_value(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _normalized_location_filter_country(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    legacy_country = _LEGACY_COUNTRY_NAME_BY_CODE.get(normalized.upper())
    if legacy_country is not None:
        return legacy_country

    return build_directory_geography(country=normalized).country


def _normalized_attorney_filter_country(value: str | None) -> str | None:
    return _normalized_location_filter_country(value)


def _location_filter_state(
    location_filter_metadata: dict[str, object],
    *,
    country_arg_name: str,
    region_arg_name: str,
) -> dict[str, str | None]:
    country = _normalized_location_filter_country(request.args.get(country_arg_name))
    region_code = _normalized_filter_value(request.args.get(region_arg_name))
    subdivision = None
    raw_regions = cast(
        dict[str, list[dict[str, str]]], location_filter_metadata.get("regions") or {}
    )
    raw_countries = cast(list[dict[str, str]], location_filter_metadata.get("countries") or [])
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


def _attorney_filter_state(attorney_filter_metadata: dict[str, object]) -> dict[str, str | None]:
    return _location_filter_state(
        attorney_filter_metadata,
        country_arg_name="country",
        region_arg_name="region",
    )


def _newsroom_filter_state(newsroom_filter_metadata: dict[str, object]) -> dict[str, str | None]:
    return _location_filter_state(
        newsroom_filter_metadata,
        country_arg_name="newsroom_country",
        region_arg_name="newsroom_region",
    )


def _all_filter_state(all_filter_metadata: dict[str, object]) -> dict[str, str | None]:
    filter_state = _location_filter_state(
        all_filter_metadata,
        country_arg_name="all_country",
        region_arg_name="all_region",
    )
    raw_listing_types = cast(list[dict[str, str]], all_filter_metadata.get("listing_types") or [])
    available_listing_types = {str(option["code"]) for option in raw_listing_types}
    available_listing_types_by_casefold = {
        listing_type.casefold(): listing_type for listing_type in available_listing_types
    }
    listing_type = _normalized_filter_value(request.args.get("all_listing_type"))
    if listing_type is not None:
        listing_type = available_listing_types_by_casefold.get(listing_type.casefold())

    return {
        **filter_state,
        "listing_type": listing_type,
    }


def _geography_matches_location_filters(
    geography: DirectoryListingGeography, filter_state: dict[str, str | None]
) -> bool:
    countries = getattr(geography, "countries", ()) or (
        (geography.country,) if geography.country is not None else ()
    )
    if filter_state["country"] and filter_state["country"] not in countries:
        return False

    if filter_state["region"] and geography.subdivision != filter_state["region"]:
        return False

    return True


def _listing_matches_location_filters(
    listing: PublicRecordListing | NewsroomDirectoryListing,
    filter_state: dict[str, str | None],
) -> bool:
    return _geography_matches_location_filters(listing.geography, filter_state)


def _listing_matches_attorney_filters(
    listing: PublicRecordListing, filter_state: dict[str, str | None]
) -> bool:
    return _listing_matches_location_filters(listing, filter_state)


def _newsroom_listing_matches_filters(
    listing: NewsroomDirectoryListing, filter_state: dict[str, str | None]
) -> bool:
    return _listing_matches_location_filters(listing, filter_state)


def _username_matches_location_filters(
    username: Username, filter_state: dict[str, str | None]
) -> bool:
    return _geography_matches_location_filters(_username_geography(username), filter_state)


def _username_matches_attorney_filters(
    username: Username, filter_state: dict[str, str | None]
) -> bool:
    return _username_matches_location_filters(username, filter_state)


def _username_matches_newsroom_filters(
    username: Username, filter_state: dict[str, str | None]
) -> bool:
    return _username_matches_location_filters(username, filter_state)


def _filter_directory_listings(
    listings: Sequence[PublicRecordListing | NewsroomDirectoryListing],
    filter_state: dict[str, str | None],
) -> list[PublicRecordListing | NewsroomDirectoryListing]:
    return [
        listing for listing in listings if _listing_matches_location_filters(listing, filter_state)
    ]


def _filter_public_record_listings(
    listings: list[PublicRecordListing] | tuple[PublicRecordListing, ...],
    filter_state: dict[str, str | None],
) -> list[PublicRecordListing]:
    return cast(list[PublicRecordListing], _filter_directory_listings(listings, filter_state))


def _filter_newsroom_listings(
    listings: list[NewsroomDirectoryListing] | tuple[NewsroomDirectoryListing, ...],
    filter_state: dict[str, str | None],
) -> list[NewsroomDirectoryListing]:
    return cast(list[NewsroomDirectoryListing], _filter_directory_listings(listings, filter_state))


def _location_filter_metadata_for_geographies(
    geographies: Sequence[DirectoryListingGeography],
) -> dict[str, object]:
    countries: dict[str, int] = {}
    regions: dict[str, dict[str, dict[str, object]]] = {}

    def add_geography(geography: DirectoryListingGeography) -> None:
        country = geography.country
        subdivision = geography.subdivision
        subdivision_code = geography.subdivision_code
        countries_for_listing = getattr(geography, "countries", ()) or (
            (country,) if country is not None else ()
        )

        if not countries_for_listing:
            return

        for listed_country in countries_for_listing:
            countries[listed_country] = countries.get(listed_country, 0) + 1

        if country is None or subdivision is None or subdivision_code is None:
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

    for geography in geographies:
        add_geography(geography)

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


def _location_filter_metadata(
    listings: Sequence[PublicRecordListing | NewsroomDirectoryListing],
    usernames: Sequence[Username] = (),
) -> dict[str, object]:
    return _location_filter_metadata_for_geographies(
        [
            *(listing.geography for listing in listings),
            *(_username_geography(username) for username in usernames),
        ]
    )


def _attorney_filter_metadata(
    listings: list[PublicRecordListing] | tuple[PublicRecordListing, ...],
    attorney_usernames: list[Username] | tuple[Username, ...] = (),
) -> dict[str, object]:
    return _location_filter_metadata(listings, attorney_usernames)


def _newsroom_filter_metadata(
    listings: list[NewsroomDirectoryListing] | tuple[NewsroomDirectoryListing, ...],
    newsroom_usernames: list[Username] | tuple[Username, ...] = (),
) -> dict[str, object]:
    return _location_filter_metadata(listings, newsroom_usernames)


def _empty_all_filter_metadata() -> dict[str, object]:
    return {
        "countries": [],
        "regions": {},
        "listing_types": [
            {"code": code, "label": label, "count": 0} for code, label in _ALL_LISTING_TYPE_LABELS
        ],
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


def _is_self_reported_newsroom(username: Username) -> bool:
    return getattr(username.user, "account_category", None) == AccountCategory.NEWSROOM.value


def _show_directory_caution_badge(username: Username) -> bool:
    return show_directory_caution_badge(
        username.display_name or username.username,
        is_admin=username.user.is_admin,
        is_verified=username.is_verified,
        is_cautious=bool(getattr(username.user, "is_cautious", False)),
    )


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
        "show_caution_badge": _show_directory_caution_badge(username),
        "has_pgp_key": bool(user.pgp_key),
        "is_public_record": False,
        "is_globaleaks": False,
        "is_newsroom": False,
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
        "show_caution_badge": False,
        "has_pgp_key": False,
        "is_public_record": True,
        "is_globaleaks": False,
        "is_newsroom": False,
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
        "show_caution_badge": False,
        "has_pgp_key": False,
        "is_public_record": False,
        "is_globaleaks": True,
        "is_newsroom": False,
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


def _newsroom_row(listing: NewsroomDirectoryListing) -> dict[str, object | None]:
    geography = listing.geography
    return {
        "entry_type": "newsroom",
        "primary_username": None,
        "display_name": listing.name,
        "bio": listing.description,
        "account_category": None,
        "account_category_label": None,
        "is_admin": False,
        "is_verified": False,
        "show_caution_badge": False,
        "has_pgp_key": False,
        "is_public_record": False,
        "is_globaleaks": False,
        "is_newsroom": True,
        "is_securedrop": False,
        "is_automated": listing.is_automated,
        "message_capable": listing.message_capable,
        "meta": listing.website or listing.directory_url,
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
        "profile_url": url_for("newsroom_listing", slug=listing.slug),
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
        "show_caution_badge": False,
        "has_pgp_key": False,
        "is_public_record": False,
        "is_globaleaks": False,
        "is_newsroom": False,
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


def _build_all_directory_entries(
    usernames: Sequence[Username],
    public_record_listings: Sequence[PublicRecordListing],
    globaleaks_listings: Sequence[GlobaLeaksDirectoryListing],
    newsroom_listings: Sequence[NewsroomDirectoryListing],
    securedrop_listings: Sequence[SecureDropDirectoryListing],
) -> list[dict[str, object | None]]:
    return [
        *[_directory_user_row(username) for username in usernames],
        *[_public_record_row(listing) for listing in public_record_listings],
        *[_globaleaks_row(listing) for listing in globaleaks_listings],
        *[_newsroom_row(listing) for listing in newsroom_listings],
        *[_securedrop_row(listing) for listing in securedrop_listings],
    ]


def _all_directory_entry_geography(
    entry: dict[str, object | None],
) -> DirectoryListingGeography:
    return build_directory_geography(
        countries=cast(list[str] | tuple[str, ...], entry.get("countries") or ()),
        city=cast(str | None, entry.get("city")),
        country=cast(str | None, entry.get("country")),
        subdivision=cast(str | None, entry.get("subdivision")),
    )


def _all_directory_entry_matches_listing_type(
    entry: dict[str, object | None], listing_type: str
) -> bool:
    if listing_type == "verified":
        return entry.get("entry_type") == "user" and bool(entry.get("is_verified"))

    if listing_type == "attorneys":
        return bool(entry.get("is_public_record")) or (
            entry.get("entry_type") == "user"
            and entry.get("account_category") == AccountCategory.LAWYER.value
        )

    if listing_type == "newsrooms":
        return bool(entry.get("is_newsroom")) or (
            entry.get("entry_type") == "user"
            and entry.get("account_category") == AccountCategory.NEWSROOM.value
        )

    if listing_type == "securedrop":
        return bool(entry.get("is_securedrop"))

    if listing_type == "globaleaks":
        return bool(entry.get("is_globaleaks"))

    return False


def _all_filter_metadata(
    entries: Sequence[dict[str, object | None]],
) -> dict[str, object]:
    metadata = _location_filter_metadata_for_geographies(
        [_all_directory_entry_geography(entry) for entry in entries]
    )
    listing_type_counts = {
        code: sum(1 for entry in entries if _all_directory_entry_matches_listing_type(entry, code))
        for code, _label in _ALL_LISTING_TYPE_LABELS
    }

    return {
        **metadata,
        "listing_types": [
            {"code": code, "label": label, "count": listing_type_counts[code]}
            for code, label in _ALL_LISTING_TYPE_LABELS
        ],
    }


def _all_directory_entry_matches_filters(
    entry: dict[str, object | None], filter_state: dict[str, str | None]
) -> bool:
    listing_type = filter_state.get("listing_type")
    if listing_type and not _all_directory_entry_matches_listing_type(entry, listing_type):
        return False

    return _geography_matches_location_filters(_all_directory_entry_geography(entry), filter_state)


def _filter_all_directory_entries(
    entries: Sequence[dict[str, object | None]],
    filter_state: dict[str, str | None],
) -> list[dict[str, object | None]]:
    return [entry for entry in entries if _all_directory_entry_matches_filters(entry, filter_state)]


def _all_directory_entry_identity(entry: dict[str, object | None]) -> str:
    return str(entry.get("display_name") or entry.get("primary_username") or "")


def _all_directory_entry_sort_key(entry: dict[str, object | None]) -> tuple[bool, bool, str, str]:
    is_admin = bool(entry.get("is_admin"))
    show_caution_badge = bool(entry.get("show_caution_badge"))
    sort_identity = _all_directory_entry_identity(entry)
    normalized_identity = unicodedata.normalize("NFKC", sort_identity).strip()
    transliterated_identity = unidecode(normalized_identity).casefold()
    return not is_admin, show_caution_badge, transliterated_identity, normalized_identity.casefold()


def _all_directory_entry_client_sort_fields(
    entry: dict[str, object | None],
) -> dict[str, str]:
    _, _, transliterated_identity, normalized_identity = _all_directory_entry_sort_key(entry)
    return {
        "all_tab_sort_transliterated": transliterated_identity,
        "all_tab_sort_normalized": normalized_identity,
    }


def _directory_filter_clear_url(*param_names: str) -> str:
    query_items = [
        (key, value) for key, value in request.args.items(multi=True) if key not in param_names
    ]
    if not query_items:
        return url_for("directory")

    return f"{url_for('directory')}?{urlencode(query_items, doseq=True)}"


def _newsroom_automated_sources(
    listings: Sequence[NewsroomDirectoryListing],
) -> list[dict[str, str]]:
    sources_by_label: dict[str, str] = {}
    for listing in listings:
        if not listing.source_label or not listing.source_url:
            continue
        sources_by_label.setdefault(listing.source_label, listing.source_url)

    return [
        {"label": label, "url": sources_by_label[label]}
        for label in sorted(sources_by_label, key=str.casefold)
    ]


def register_directory_routes(app: Flask) -> None:
    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        usernames = list(get_directory_usernames())
        attorney_usernames = [
            username for username in usernames if _is_self_reported_attorney(username)
        ]
        newsroom_usernames = [
            username for username in usernames if _is_self_reported_newsroom(username)
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
        if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            all_newsroom_listings = list(get_newsroom_directory_listings())
            newsroom_automated_sources = _newsroom_automated_sources(all_newsroom_listings)
            newsroom_filter_metadata = _newsroom_filter_metadata(
                all_newsroom_listings, newsroom_usernames
            )
            newsroom_filter_state = _newsroom_filter_state(newsroom_filter_metadata)
            filtered_newsroom_usernames = [
                username
                for username in newsroom_usernames
                if _username_matches_newsroom_filters(username, newsroom_filter_state)
            ]
            newsroom_listings = _filter_newsroom_listings(
                all_newsroom_listings, newsroom_filter_state
            )
        else:
            newsroom_automated_sources = []
            newsroom_filter_metadata = {"countries": [], "regions": {}}
            newsroom_filter_state = {"country": None, "region": None, "region_code": None}
            filtered_newsroom_usernames = newsroom_usernames
            all_newsroom_listings = []
            newsroom_listings = []
        pgp_usernames = [username for username in usernames if username.user.pgp_key]
        info_usernames = [username for username in usernames if not username.user.pgp_key]
        verified_pgp_usernames = [username for username in pgp_usernames if username.is_verified]
        verified_info_usernames = [username for username in info_usernames if username.is_verified]
        all_directory_entries = _build_all_directory_entries(
            usernames,
            all_public_record_listings,
            globaleaks_listings,
            all_newsroom_listings,
            securedrop_listings,
        )
        legacy_filtered_all_directory_entries = [
            *[
                _directory_user_row(username)
                for username in usernames
                if not _is_self_reported_newsroom(username)
                or _username_matches_newsroom_filters(username, newsroom_filter_state)
            ],
            *[_public_record_row(listing) for listing in filtered_public_record_listings],
            *[_globaleaks_row(listing) for listing in globaleaks_listings],
            *[_newsroom_row(listing) for listing in newsroom_listings],
            *[_securedrop_row(listing) for listing in securedrop_listings],
        ]
        if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            all_filter_metadata = _all_filter_metadata(all_directory_entries)
            all_filter_state = _all_filter_state(all_filter_metadata)
            has_active_all_filters = bool(
                all_filter_state["country"]
                or all_filter_state["region_code"]
                or all_filter_state["listing_type"]
            )
            filtered_all_directory_entries = (
                _filter_all_directory_entries(all_directory_entries, all_filter_state)
                if has_active_all_filters
                else legacy_filtered_all_directory_entries
            )
        else:
            all_filter_metadata = _empty_all_filter_metadata()
            all_filter_state = {
                "country": None,
                "region": None,
                "region_code": None,
                "listing_type": None,
            }
            filtered_all_directory_entries = legacy_filtered_all_directory_entries
        filtered_all_directory_entries.sort(key=_all_directory_entry_sort_key)
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
            attorney_filter_clear_url=_directory_filter_clear_url("country", "region"),
            globaleaks_listings=globaleaks_listings,
            globaleaks_total_count=len(globaleaks_listings),
            newsroom_usernames=filtered_newsroom_usernames,
            newsroom_listings=newsroom_listings,
            newsroom_automated_sources=newsroom_automated_sources,
            newsroom_total_count=len(filtered_newsroom_usernames) + len(newsroom_listings),
            newsroom_filter_metadata=newsroom_filter_metadata,
            newsroom_filter_state=newsroom_filter_state,
            newsroom_filter_clear_url=_directory_filter_clear_url(
                "newsroom_country", "newsroom_region"
            ),
            all_filter_metadata=all_filter_metadata,
            all_filter_state=all_filter_state,
            all_filter_clear_url=_directory_filter_clear_url(
                "all_country", "all_region", "all_listing_type"
            ),
            securedrop_listings=securedrop_listings,
            securedrop_total_count=len(securedrop_listings),
            all_directory_entries=filtered_all_directory_entries,
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

    @app.route("/directory/newsrooms/<slug>")
    def newsroom_listing(slug: str) -> Response | str:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            abort(404)

        listing = get_newsroom_directory_listing(slug)
        if listing is None:
            abort(404)

        return render_template("directory_newsroom.html", listing=listing)

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

        public_record_listings = get_public_record_listings()
        attorney_usernames = tuple(
            username for username in get_directory_usernames() if _is_self_reported_attorney(username)
        )
        attorney_filter_state = _attorney_filter_state(
            _attorney_filter_metadata(public_record_listings, attorney_usernames)
        )

        return _attorney_filter_metadata(
            _filter_public_record_listings(public_record_listings, attorney_filter_state),
            tuple(
                username
                for username in attorney_usernames
                if _username_matches_attorney_filters(username, attorney_filter_state)
            ),
        )

    @app.route("/directory/newsroom-filters.json")
    def directory_newsroom_filters() -> dict[str, object]:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            return {
                "countries": [],
                "regions": {},
            }

        newsroom_listings = get_newsroom_directory_listings()
        newsroom_usernames = tuple(
            username for username in get_directory_usernames() if _is_self_reported_newsroom(username)
        )
        newsroom_filter_state = _newsroom_filter_state(
            _newsroom_filter_metadata(newsroom_listings, newsroom_usernames)
        )

        return _newsroom_filter_metadata(
            _filter_newsroom_listings(newsroom_listings, newsroom_filter_state),
            tuple(
                username
                for username in newsroom_usernames
                if _username_matches_newsroom_filters(username, newsroom_filter_state)
            ),
        )

    @app.route("/directory/all-filters.json")
    def directory_all_filters() -> dict[str, object]:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            return _empty_all_filter_metadata()

        all_directory_entries = _build_all_directory_entries(
            list(get_directory_usernames()),
            list(get_public_record_listings()),
            list(get_globaleaks_directory_listings()),
            list(get_newsroom_directory_listings()),
            list(get_securedrop_directory_listings()),
        )
        all_filter_state = _all_filter_state(_all_filter_metadata(all_directory_entries))
        return _all_filter_metadata(
            _filter_all_directory_entries(all_directory_entries, all_filter_state)
        )

    @app.route("/directory/users.json")
    def directory_users() -> list[dict[str, object | None]]:
        directory_usernames = list(get_directory_usernames())
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
        if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            newsroom_listings = list(get_newsroom_directory_listings())
            newsroom_filter_state = _newsroom_filter_state(
                _newsroom_filter_metadata(
                    newsroom_listings,
                    tuple(
                        username
                        for username in directory_usernames
                        if _is_self_reported_newsroom(username)
                    ),
                )
            )
        else:
            newsroom_listings = []
            newsroom_filter_state = {"country": None, "region": None, "region_code": None}
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
        newsroom_rows = (
            [
                _newsroom_row(listing)
                for listing in _filter_newsroom_listings(newsroom_listings, newsroom_filter_state)
            ]
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        securedrop_rows = (
            [_securedrop_row(listing) for listing in get_securedrop_directory_listings()]
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        all_directory_entries = (
            _build_all_directory_entries(
                directory_usernames,
                public_record_listings,
                list(get_globaleaks_directory_listings())
                if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
                else [],
                newsroom_listings,
                list(get_securedrop_directory_listings())
                if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
                else [],
            )
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else []
        )
        all_filter_state = (
            _all_filter_state(_all_filter_metadata(all_directory_entries))
            if app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]
            else {"country": None, "region": None, "region_code": None, "listing_type": None}
        )
        has_active_all_filters = bool(
            all_filter_state["country"]
            or all_filter_state["region_code"]
            or all_filter_state["listing_type"]
        )
        entries = (
            _filter_all_directory_entries(all_directory_entries, all_filter_state)
            if has_active_all_filters
            else [
                *[
                    _directory_user_row(username)
                    for username in directory_usernames
                    if not _is_self_reported_newsroom(username)
                    or _username_matches_newsroom_filters(username, newsroom_filter_state)
                ],
                *public_record_rows,
                *globaleaks_rows,
                *newsroom_rows,
                *securedrop_rows,
            ]
        )
        return [
            {
                **entry,
                **_all_directory_entry_client_sort_fields(entry),
            }
            for entry in entries
        ]
