from __future__ import annotations

from dataclasses import dataclass

_USA = "United States"
_COUNTRY_ALIASES = {
    "u.s.": _USA,
    "u.s.a.": _USA,
    "us": _USA,
    "usa": _USA,
    "united states of america": _USA,
}
_US_SUBDIVISION_NAMES = {
    "AK": "Alaska",
    "AL": "Alabama",
    "AR": "Arkansas",
    "AZ": "Arizona",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DC": "District of Columbia",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "IA": "Iowa",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "MA": "Massachusetts",
    "MD": "Maryland",
    "ME": "Maine",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MO": "Missouri",
    "MS": "Mississippi",
    "MT": "Montana",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "NE": "Nebraska",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NV": "Nevada",
    "NY": "New York",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VA": "Virginia",
    "VT": "Vermont",
    "WA": "Washington",
    "WI": "Wisconsin",
    "WV": "West Virginia",
    "WY": "Wyoming",
}
_US_SUBDIVISION_CODES = frozenset(_US_SUBDIVISION_NAMES)
_US_SUBDIVISION_CODES_BY_NAME = {
    subdivision_name.casefold(): subdivision_code
    for subdivision_code, subdivision_name in _US_SUBDIVISION_NAMES.items()
}
US_SUBDIVISION_NAMES = _US_SUBDIVISION_NAMES


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _normalize_country(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None

    return _COUNTRY_ALIASES.get(normalized.casefold(), normalized)


def _normalize_subdivision(value: str | None, country: str | None) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None

    if country == _USA:
        return _US_SUBDIVISION_NAMES.get(normalized.upper(), normalized)

    return normalized


def _normalize_subdivision_code(value: str | None, country: str | None) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None

    if country == _USA:
        subdivision_code = normalized.upper()
        if subdivision_code in _US_SUBDIVISION_CODES:
            return subdivision_code

        return _US_SUBDIVISION_CODES_BY_NAME.get(normalized.casefold())

    return normalized


@dataclass(frozen=True)
class DirectoryListingGeography:
    """Normalized location fields shared by all automated directory listings."""

    city: str | None = None
    country: str | None = None
    subdivision: str | None = None
    subdivision_code: str | None = None
    countries: tuple[str, ...] = ()

    @property
    def location(self) -> str:
        parts: list[str] = []

        if self.city:
            parts.append(self.city)
            if self.subdivision:
                parts.append(self.subdivision)
            if self.country:
                parts.append(self.country)
        elif self.subdivision:
            parts.append(self.subdivision)
            if self.country:
                parts.append(self.country)
        elif self.countries:
            parts.extend(self.countries)
        elif self.country:
            parts.append(self.country)

        return ", ".join(parts) if parts else "Unknown"


def build_public_record_geography(
    *,
    city: str | None,
    state: str | None,
    country: str | None = None,
    subdivision: str | None = None,
) -> DirectoryListingGeography:
    # Legacy attorney seeds overloaded `state` with either a US state code or a country name.
    normalized_city = _normalize_text(city)
    normalized_country = _normalize_country(country)
    normalized_subdivision = _normalize_subdivision(subdivision, normalized_country)
    normalized_subdivision_code = _normalize_subdivision_code(subdivision, normalized_country)
    normalized_state = _normalize_text(state)

    if normalized_subdivision is None and normalized_state:
        if normalized_country is not None and normalized_state != normalized_country:
            normalized_subdivision = _normalize_subdivision(normalized_state, normalized_country)
            normalized_subdivision_code = _normalize_subdivision_code(
                normalized_state, normalized_country
            )
        elif normalized_country is None:
            state_code = normalized_state.upper()
            if state_code in _US_SUBDIVISION_CODES:
                normalized_country = _USA
                normalized_subdivision = _US_SUBDIVISION_NAMES[state_code]
                normalized_subdivision_code = state_code
            else:
                normalized_country = _normalize_country(normalized_state)

    countries = (normalized_country,) if normalized_country else ()
    return DirectoryListingGeography(
        city=normalized_city,
        country=normalized_country,
        subdivision=normalized_subdivision,
        subdivision_code=normalized_subdivision_code,
        countries=countries,
    )


def build_directory_geography(
    *,
    countries: tuple[str, ...] | list[str] = (),
    city: str | None = None,
    country: str | None = None,
    subdivision: str | None = None,
) -> DirectoryListingGeography:
    # Non-attorney sources may only provide country-level scopes today, but they should
    # populate `city`, `country`, and `subdivision` directly as better data becomes available.
    normalized_countries = tuple(
        value for value in (_normalize_country(item) for item in countries) if value is not None
    )
    normalized_city = _normalize_text(city)
    normalized_country = _normalize_country(country)
    normalized_subdivision = _normalize_subdivision(subdivision, normalized_country)
    normalized_subdivision_code = _normalize_subdivision_code(subdivision, normalized_country)

    if normalized_country is None and len(normalized_countries) == 1:
        normalized_country = normalized_countries[0]
        normalized_subdivision = _normalize_subdivision(normalized_subdivision, normalized_country)
        normalized_subdivision_code = _normalize_subdivision_code(
            normalized_subdivision, normalized_country
        )

    countries_value = normalized_countries
    if not countries_value and normalized_country:
        countries_value = (normalized_country,)

    return DirectoryListingGeography(
        city=normalized_city,
        country=normalized_country,
        subdivision=normalized_subdivision,
        subdivision_code=normalized_subdivision_code,
        countries=countries_value,
    )
