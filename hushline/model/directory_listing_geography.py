from __future__ import annotations

from dataclasses import dataclass

_USA = "USA"
_US_SUBDIVISION_CODES = frozenset(
    {
        "AK",
        "AL",
        "AR",
        "AZ",
        "CA",
        "CO",
        "CT",
        "DC",
        "DE",
        "FL",
        "GA",
        "HI",
        "IA",
        "ID",
        "IL",
        "IN",
        "KS",
        "KY",
        "LA",
        "MA",
        "MD",
        "ME",
        "MI",
        "MN",
        "MO",
        "MS",
        "MT",
        "NC",
        "ND",
        "NE",
        "NH",
        "NJ",
        "NM",
        "NV",
        "NY",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VA",
        "VT",
        "WA",
        "WI",
        "WV",
        "WY",
    }
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True)
class DirectoryListingGeography:
    """Normalized location fields shared by all automated directory listings."""

    city: str | None = None
    country: str | None = None
    subdivision: str | None = None
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
    normalized_country = _normalize_text(country)
    normalized_subdivision = _normalize_text(subdivision)
    normalized_state = _normalize_text(state)

    if normalized_subdivision is None and normalized_state:
        if normalized_country is not None and normalized_state != normalized_country:
            normalized_subdivision = normalized_state
        elif normalized_country is None:
            state_code = normalized_state.upper()
            if state_code in _US_SUBDIVISION_CODES:
                normalized_country = _USA
                normalized_subdivision = state_code
            else:
                normalized_country = normalized_state

    countries = (normalized_country,) if normalized_country else ()
    return DirectoryListingGeography(
        city=normalized_city,
        country=normalized_country,
        subdivision=normalized_subdivision,
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
        value for value in (_normalize_text(item) for item in countries) if value is not None
    )
    normalized_city = _normalize_text(city)
    normalized_country = _normalize_text(country)
    normalized_subdivision = _normalize_text(subdivision)

    if normalized_country is None and len(normalized_countries) == 1:
        normalized_country = normalized_countries[0]

    countries_value = normalized_countries
    if not countries_value and normalized_country:
        countries_value = (normalized_country,)

    return DirectoryListingGeography(
        city=normalized_city,
        country=normalized_country,
        subdivision=normalized_subdivision,
        countries=countries_value,
    )
