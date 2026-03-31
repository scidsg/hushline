import unicodedata
from dataclasses import dataclass
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

_GUIDED_DIRECTORY_ANY_REGION = "__any__"


@dataclass(frozen=True)
class GuidedDirectoryChoice:
    value: str
    label: str
    attorney_terms: tuple[str, ...]
    newsroom_terms: tuple[str, ...]


@dataclass(frozen=True)
class GuidedDirectoryScore:
    country_match: bool
    region_match: bool
    area_match_count: int
    industry_match_count: int


@dataclass(frozen=True)
class GuidedDirectoryRecommendationQuery:
    country: str
    region: str | None
    area_choice: GuidedDirectoryChoice
    industry_choice: GuidedDirectoryChoice
    side: str


_GUIDED_DIRECTORY_INDUSTRY_CHOICES = (
    GuidedDirectoryChoice(
        value="government-public-services",
        label="Government and public services",
        attorney_terms=(
            "Whistleblowing",
            "Whistleblower",
            "Compliance",
            "Governance",
            "Regulatory",
        ),
        newsroom_terms=(
            "Government",
            "Campaigns and elections",
            "Politics",
            "Politics / policy / democracy",
            "Voting access and rights",
        ),
    ),
    GuidedDirectoryChoice(
        value="business-finance",
        label="Business, finance, and contracting",
        attorney_terms=(
            "Consumer",
            "Consumer Protection",
            "False Claims",
            "Fraud",
            "Qui Tam",
            "Securities",
            "IRS",
            "SEC",
            "Antitrust",
        ),
        newsroom_terms=("Business and entrepreneurship", "Economic Development"),
    ),
    GuidedDirectoryChoice(
        value="workplace",
        label="Workplace or employer context",
        attorney_terms=("Employment", "Retaliation", "Discrimination", "Civil Rights"),
        newsroom_terms=("Worker's Rights", "Inequality and justice", "Equity"),
    ),
    GuidedDirectoryChoice(
        value="health",
        label="Health and medicine",
        attorney_terms=("Regulatory", "Compliance", "Whistleblowing", "Whistleblower"),
        newsroom_terms=("Health and medicine", "Health"),
    ),
    GuidedDirectoryChoice(
        value="education",
        label="Education",
        attorney_terms=("Employment", "Civil Rights", "Public Interest"),
        newsroom_terms=("Education (K - 12)", "Higher Education"),
    ),
    GuidedDirectoryChoice(
        value="environment-infrastructure",
        label="Environment and infrastructure",
        attorney_terms=("Environmental", "Regulatory", "Compliance"),
        newsroom_terms=(
            "Environment and climate",
            "Climate",
            "Water quality and access",
            "Transportation",
            "Food and agriculture",
        ),
    ),
)

_GUIDED_DIRECTORY_AREA_CHOICES = (
    GuidedDirectoryChoice(
        value="fraud-accountability",
        label="Fraud, corruption, and accountability",
        attorney_terms=(
            "Whistleblowing",
            "Whistleblower",
            "False Claims",
            "Fraud",
            "Qui Tam",
            "Compliance",
            "Governance",
            "Investigations",
            "Securities",
            "IRS",
            "SEC",
        ),
        newsroom_terms=(
            "Government",
            "Campaigns and elections",
            "Politics",
            "Politics / policy / democracy",
            "Criminal Justice",
            "Business and entrepreneurship",
            "Economic Development",
        ),
    ),
    GuidedDirectoryChoice(
        value="workplace-rights",
        label="Workplace retaliation and rights",
        attorney_terms=("Employment", "Retaliation", "Discrimination", "Civil Rights"),
        newsroom_terms=("Worker's Rights", "Inequality and justice", "Equity"),
    ),
    GuidedDirectoryChoice(
        value="environment-health",
        label="Environment, health, and public safety",
        attorney_terms=("Environmental", "Regulatory", "Compliance"),
        newsroom_terms=(
            "Environment and climate",
            "Climate",
            "Health and medicine",
            "Health",
            "Water quality and access",
            "Food and agriculture",
        ),
    ),
    GuidedDirectoryChoice(
        value="civil-rights",
        label="Civil rights and community harm",
        attorney_terms=("Civil Rights", "Discrimination", "Retaliation", "Public Interest"),
        newsroom_terms=(
            "Inequality and justice",
            "Racial and ethnic identity",
            "Immigration",
            "Refugees",
            "LGBTQIA+",
        ),
    ),
)

_GUIDED_DIRECTORY_INDUSTRY_BY_VALUE = {
    choice.value: choice for choice in _GUIDED_DIRECTORY_INDUSTRY_CHOICES
}
_GUIDED_DIRECTORY_AREA_BY_VALUE = {
    choice.value: choice for choice in _GUIDED_DIRECTORY_AREA_CHOICES
}


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


def _location_filter_metadata(
    listings: Sequence[PublicRecordListing | NewsroomDirectoryListing],
    usernames: Sequence[Username] = (),
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

    for listing in listings:
        add_geography(listing.geography)

    for username in usernames:
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


def _guided_directory_choice(
    choices_by_value: dict[str, GuidedDirectoryChoice], value: str | None
) -> GuidedDirectoryChoice | None:
    normalized = _normalized_filter_value(value)
    if normalized is None:
        return None
    return choices_by_value.get(normalized)


def _guided_directory_country_options(
    *filter_metadata: dict[str, object],
) -> list[dict[str, str]]:
    countries_by_casefold: dict[str, str] = {}
    for metadata in filter_metadata:
        for option in cast(list[dict[str, str]], metadata.get("countries") or []):
            country = str(option["code"])
            countries_by_casefold.setdefault(country.casefold(), country)

    return [
        {"code": country, "label": country}
        for country in sorted(countries_by_casefold.values(), key=str.casefold)
    ]


def _guided_directory_selected_country(
    value: str | None, country_options: Sequence[dict[str, str]]
) -> str | None:
    normalized = _normalized_location_filter_country(value)
    if normalized is None:
        return None

    if not country_options:
        return normalized

    countries_by_casefold = {
        str(option["code"]).casefold(): str(option["code"]) for option in country_options
    }
    return countries_by_casefold.get(normalized.casefold())


def _guided_directory_region_options(
    country: str | None, *filter_metadata: dict[str, object]
) -> list[dict[str, str]]:
    if country is None:
        return []

    region_labels_by_code: dict[str, str] = {}
    for metadata in filter_metadata:
        raw_regions = cast(dict[str, list[dict[str, str]]], metadata.get("regions") or {}).get(
            country, []
        )
        for region in raw_regions:
            code = str(region["code"])
            region_labels_by_code.setdefault(code, str(region["label"]))

    return [
        {"code": code, "label": region_labels_by_code[code]}
        for code in sorted(
            region_labels_by_code,
            key=lambda code: region_labels_by_code[code].casefold(),
        )
    ]


def _guided_directory_region_state(
    value: str | None,
    region_options: Sequence[dict[str, str]],
) -> dict[str, str | bool | None]:
    if not region_options:
        return {"answered": True, "code": None, "label": None, "value": None}

    if value is None:
        return {"answered": False, "code": None, "label": None, "value": None}

    normalized = _normalized_filter_value(value)
    if normalized is None:
        return {"answered": False, "code": None, "label": None, "value": None}

    if normalized == _GUIDED_DIRECTORY_ANY_REGION:
        return {
            "answered": True,
            "code": None,
            "label": None,
            "value": _GUIDED_DIRECTORY_ANY_REGION,
        }

    regions_by_casefold = {str(option["code"]).casefold(): option for option in region_options}
    matched = regions_by_casefold.get(normalized.casefold())
    if matched is None:
        return {"answered": False, "code": None, "label": None, "value": None}

    return {
        "answered": True,
        "code": str(matched["code"]),
        "label": str(matched["label"]),
        "value": str(matched["code"]),
    }


def _guided_directory_row_terms(row: dict[str, object | None]) -> set[str]:
    return {
        str(term).casefold()
        for term in cast(list[str], row.get("practice_tags") or [])
        if str(term).strip()
    }


def _guided_directory_row_countries(row: dict[str, object | None]) -> tuple[str, ...]:
    countries = tuple(
        str(country)
        for country in cast(list[str], row.get("countries") or [])
        if str(country).strip()
    )
    if countries:
        return countries

    country = row.get("country")
    if isinstance(country, str) and country.strip():
        return (country,)

    return ()


def _guided_directory_identity_sort_key(row: dict[str, object | None]) -> tuple[str, str]:
    sort_identity = _all_directory_entry_identity(row)
    normalized_identity = unicodedata.normalize("NFKC", sort_identity).strip()
    transliterated_identity = unidecode(normalized_identity).casefold()
    return transliterated_identity, normalized_identity.casefold()


def _guided_directory_candidate_score(
    row: dict[str, object | None],
    *,
    query: GuidedDirectoryRecommendationQuery,
) -> GuidedDirectoryScore:
    row_countries = _guided_directory_row_countries(row)
    row_region = cast(str | None, row.get("subdivision"))
    row_terms = _guided_directory_row_terms(row)
    area_terms = (
        query.area_choice.attorney_terms
        if query.side == "attorney"
        else query.area_choice.newsroom_terms
    )
    industry_terms = (
        query.industry_choice.attorney_terms
        if query.side == "attorney"
        else query.industry_choice.newsroom_terms
    )
    area_match_count = len(
        row_terms.intersection(term.casefold() for term in area_terms if term.strip())
    )
    industry_match_count = len(
        row_terms.intersection(term.casefold() for term in industry_terms if term.strip())
    )

    return GuidedDirectoryScore(
        country_match=query.country in row_countries,
        region_match=query.region is not None and row_region == query.region,
        area_match_count=area_match_count,
        industry_match_count=industry_match_count,
    )


def _guided_directory_recommendation_sort_key(
    row: dict[str, object | None],
    *,
    score: GuidedDirectoryScore,
) -> tuple[int, int, int, int, int, int, int, str, str]:
    transliterated_identity, normalized_identity = _guided_directory_identity_sort_key(row)
    return (
        -int(score.country_match),
        -int(score.region_match),
        -(1 if score.area_match_count > 0 else 0),
        -score.area_match_count,
        -(1 if score.industry_match_count > 0 else 0),
        -score.industry_match_count,
        -int(bool(row.get("message_capable"))),
        transliterated_identity,
        normalized_identity,
    )


def _guided_directory_select_recommendation(
    rows: Sequence[dict[str, object | None]],
    *,
    query: GuidedDirectoryRecommendationQuery,
) -> tuple[dict[str, object | None] | None, GuidedDirectoryScore | None]:
    if not rows:
        return None, None

    scored_rows = [(row, _guided_directory_candidate_score(row, query=query)) for row in rows]
    ranked_rows = sorted(
        scored_rows,
        key=lambda item: _guided_directory_recommendation_sort_key(
            item[0],
            score=item[1],
        ),
    )
    selected_row, selected_score = ranked_rows[0]
    return selected_row, selected_score


def _guided_directory_recommendation_reason(
    *,
    query: GuidedDirectoryRecommendationQuery,
    score: GuidedDirectoryScore,
) -> str:
    matched_on: list[str] = []
    notes: list[str] = []

    if score.country_match:
        matched_on.append(query.country)
    elif query.country:
        notes.append("No country match was available in this candidate pool.")

    if query.region:
        if score.region_match:
            matched_on.append(query.region)
        else:
            notes.append(
                "No region match was available, so this fell back to country " "and stable sorting."
            )

    if score.area_match_count > 0:
        matched_on.append(query.area_choice.label)
    else:
        notes.append("Structured area-of-interest metadata was not a strong match on this side.")

    if score.industry_match_count == 0:
        notes.append(
            "Industry was only used as a soft tie-breaker when structured metadata "
            "was available."
        )

    if matched_on:
        return " ".join([f"Matched on {' + '.join(matched_on)}.", *notes]).strip()

    return " ".join(
        [
            "No structured location or topic match was available.",
            *notes,
            "Stable sorting broke the remaining tie.",
        ]
    ).strip()


def _guided_directory_result_type_label(row: dict[str, object | None]) -> str:
    return "Profile" if row.get("entry_type") == "user" else "Automated listing"


def _guided_directory_contactability_label(row: dict[str, object | None]) -> str:
    if row.get("entry_type") == "user":
        return "Message-capable profile" if row.get("message_capable") else "Info-only profile"
    return "Read-only listing"


def _guided_directory_view_label(row: dict[str, object | None]) -> str:
    return "View Profile" if row.get("entry_type") == "user" else "View Listing"


def _guided_directory_recommendation(
    row: dict[str, object | None] | None,
    *,
    query: GuidedDirectoryRecommendationQuery,
    score: GuidedDirectoryScore | None,
    heading: str,
) -> dict[str, object | None]:
    if row is None or score is None:
        return {
            "heading": heading,
            "display_name": "No recommendation available",
            "bio": "This candidate pool did not return any public directory entries.",
            "profile_url": None,
            "view_label": None,
            "result_type_label": None,
            "contactability_label": None,
            "why_selected": "No public candidates were available for this slot.",
        }

    return {
        "heading": heading,
        "display_name": row.get("display_name"),
        "bio": row.get("bio"),
        "profile_url": row.get("profile_url"),
        "view_label": _guided_directory_view_label(row),
        "result_type_label": _guided_directory_result_type_label(row),
        "contactability_label": _guided_directory_contactability_label(row),
        "why_selected": _guided_directory_recommendation_reason(
            query=query,
            score=score,
        ),
    }


def _guided_directory_url(
    *,
    industry: str | None = None,
    country: str | None = None,
    area: str | None = None,
    region: str | None = None,
) -> str:
    query_items = [
        (key, value)
        for key, value in (
            ("industry", industry),
            ("country", country),
            ("area", area),
            ("region", region),
        )
        if value is not None
    ]
    if not query_items:
        return url_for("directory_guided")

    return f"{url_for('directory_guided')}?{urlencode(query_items)}"


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
            newsroom_listings = []
        pgp_usernames = [username for username in usernames if username.user.pgp_key]
        info_usernames = [username for username in usernames if not username.user.pgp_key]
        verified_pgp_usernames = [username for username in pgp_usernames if username.is_verified]
        verified_info_usernames = [username for username in info_usernames if username.is_verified]
        all_directory_entries = [
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
            securedrop_listings=securedrop_listings,
            securedrop_total_count=len(securedrop_listings),
            all_directory_entries=all_directory_entries,
            logged_in=logged_in,
        )

    @app.route("/directory/guided")
    def directory_guided() -> Response | str:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            abort(404)

        usernames = list(get_directory_usernames())
        attorney_usernames = [
            username for username in usernames if _is_self_reported_attorney(username)
        ]
        newsroom_usernames = [
            username for username in usernames if _is_self_reported_newsroom(username)
        ]
        public_record_listings = list(get_public_record_listings())
        newsroom_listings = list(get_newsroom_directory_listings())
        attorney_filter_metadata = _attorney_filter_metadata(
            public_record_listings, attorney_usernames
        )
        newsroom_filter_metadata = _newsroom_filter_metadata(newsroom_listings, newsroom_usernames)
        country_options = _guided_directory_country_options(
            attorney_filter_metadata, newsroom_filter_metadata
        )
        selected_industry = _guided_directory_choice(
            _GUIDED_DIRECTORY_INDUSTRY_BY_VALUE, request.args.get("industry")
        )
        selected_country = _guided_directory_selected_country(
            request.args.get("country"), country_options
        )
        selected_area = _guided_directory_choice(
            _GUIDED_DIRECTORY_AREA_BY_VALUE, request.args.get("area")
        )
        region_options = _guided_directory_region_options(
            selected_country, attorney_filter_metadata, newsroom_filter_metadata
        )
        selected_region_state = _guided_directory_region_state(
            request.args.get("region"), region_options
        )
        region_supported = bool(region_options)
        total_steps = 4 if region_supported else 3

        if selected_industry is None:
            current_step = "industry"
            step_number = 1
        elif selected_country is None:
            current_step = "country"
            step_number = 2
        elif selected_area is None:
            current_step = "area"
            step_number = 3
        elif region_supported and not selected_region_state["answered"]:
            current_step = "region"
            step_number = 4
        else:
            current_step = "results"
            step_number = total_steps

        selected_region = cast(str | None, selected_region_state["label"])
        attorney_recommendation = None
        newsroom_recommendation = None
        selected_answers: list[dict[str, str]] = []

        if current_step == "results" and selected_industry and selected_country and selected_area:
            attorney_query = GuidedDirectoryRecommendationQuery(
                country=selected_country,
                region=selected_region,
                area_choice=selected_area,
                industry_choice=selected_industry,
                side="attorney",
            )
            newsroom_query = GuidedDirectoryRecommendationQuery(
                country=selected_country,
                region=selected_region,
                area_choice=selected_area,
                industry_choice=selected_industry,
                side="newsroom",
            )
            attorney_row, attorney_score = _guided_directory_select_recommendation(
                [
                    *[_directory_user_row(username) for username in attorney_usernames],
                    *[_public_record_row(listing) for listing in public_record_listings],
                ],
                query=attorney_query,
            )
            newsroom_row, newsroom_score = _guided_directory_select_recommendation(
                [
                    *[_directory_user_row(username) for username in newsroom_usernames],
                    *[_newsroom_row(listing) for listing in newsroom_listings],
                ],
                query=newsroom_query,
            )
            attorney_recommendation = _guided_directory_recommendation(
                attorney_row,
                query=attorney_query,
                score=attorney_score,
                heading="Attorney or law-firm recommendation",
            )
            newsroom_recommendation = _guided_directory_recommendation(
                newsroom_row,
                query=newsroom_query,
                score=newsroom_score,
                heading="Newsroom recommendation",
            )
            selected_answers = [
                {
                    "label": "Industry",
                    "value": selected_industry.label,
                    "change_url": _guided_directory_url(),
                },
                {
                    "label": "Country",
                    "value": selected_country,
                    "change_url": _guided_directory_url(industry=selected_industry.value),
                },
                {
                    "label": "Area of interest",
                    "value": selected_area.label,
                    "change_url": _guided_directory_url(
                        industry=selected_industry.value,
                        country=selected_country,
                    ),
                },
            ]
            if region_supported:
                selected_answers.append(
                    {
                        "label": "State / Province / Region",
                        "value": selected_region or "No region preference",
                        "change_url": _guided_directory_url(
                            industry=selected_industry.value,
                            country=selected_country,
                            area=selected_area.value,
                        ),
                    }
                )

        back_url = None
        if current_step == "country" and selected_industry:
            back_url = _guided_directory_url()
        elif current_step == "area" and selected_industry and selected_country:
            back_url = _guided_directory_url(industry=selected_industry.value)
        elif current_step == "region" and selected_industry and selected_country and selected_area:
            back_url = _guided_directory_url(
                industry=selected_industry.value,
                country=selected_country,
            )
        elif current_step == "results" and selected_industry and selected_country and selected_area:
            if region_supported:
                back_url = _guided_directory_url(
                    industry=selected_industry.value,
                    country=selected_country,
                    area=selected_area.value,
                )
            else:
                back_url = _guided_directory_url(
                    industry=selected_industry.value,
                    country=selected_country,
                )

        return render_template(
            "directory_guided.html",
            current_step=current_step,
            step_number=step_number,
            total_steps=total_steps,
            industry_choices=_GUIDED_DIRECTORY_INDUSTRY_CHOICES,
            area_choices=_GUIDED_DIRECTORY_AREA_CHOICES,
            country_options=country_options,
            region_options=region_options,
            selected_industry=selected_industry,
            selected_country=selected_country,
            selected_area=selected_area,
            selected_region_state=selected_region_state,
            selected_answers=selected_answers,
            attorney_recommendation=attorney_recommendation,
            newsroom_recommendation=newsroom_recommendation,
            back_url=back_url,
            restart_url=_guided_directory_url(),
            directory_url=url_for("directory"),
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

        return _attorney_filter_metadata(
            get_public_record_listings(),
            tuple(
                username
                for username in get_directory_usernames()
                if _is_self_reported_attorney(username)
            ),
        )

    @app.route("/directory/newsroom-filters.json")
    def directory_newsroom_filters() -> dict[str, object]:
        if not app.config["DIRECTORY_VERIFIED_TAB_ENABLED"]:
            return {
                "countries": [],
                "regions": {},
            }

        return _newsroom_filter_metadata(
            get_newsroom_directory_listings(),
            tuple(
                username
                for username in get_directory_usernames()
                if _is_self_reported_newsroom(username)
            ),
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
        return [
            {
                **entry,
                **_all_directory_entry_client_sort_fields(entry),
            }
            for entry in [
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
        ]
