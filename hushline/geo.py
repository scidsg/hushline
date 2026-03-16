from __future__ import annotations

from functools import lru_cache

from countrystatecity_countries import (
    get_cities_of_state,
    get_countries,
    get_states_of_country,
)

_COUNTRY_ALIASES = {
    "u.s.": "United States",
    "u.s.a.": "United States",
    "u.k.": "United Kingdom",
    "uk": "United Kingdom",
    "united states of america": "United States",
    "us": "United States",
    "usa": "United States",
}


@lru_cache(maxsize=1)
def _countries() -> tuple:
    return tuple(sorted(get_countries(), key=lambda country: country.name.casefold()))


@lru_cache(maxsize=1)
def _country_name_by_casefold() -> dict[str, str]:
    country_names = {}
    for country in _countries():
        country_names[country.name.casefold()] = country.name
        country_names[country.iso2.casefold()] = country.name
        country_names[country.iso3.casefold()] = country.name
    return country_names


@lru_cache(maxsize=1)
def _country_iso2_by_name() -> dict[str, str]:
    return {country.name: country.iso2 for country in _countries()}


@lru_cache(maxsize=None)
def _states_by_country_iso2(country_iso2: str) -> tuple:
    return tuple(get_states_of_country(country_iso2))


@lru_cache(maxsize=None)
def _state_name_by_keys(country_iso2: str) -> dict[str, str]:
    state_names = {}
    for state in _states_by_country_iso2(country_iso2):
        state_names[state.name.casefold()] = state.name
        state_names[state.state_code.casefold()] = state.name
        if state.iso3166_2:
            state_names[state.iso3166_2.casefold()] = state.name
    return state_names


@lru_cache(maxsize=None)
def _state_name_by_code(country_iso2: str) -> dict[str, str]:
    return {state.state_code: state.name for state in _states_by_country_iso2(country_iso2)}


@lru_cache(maxsize=None)
def _state_options_by_country(country_iso2: str) -> tuple[dict[str, str], ...]:
    return tuple(
        sorted(
            (
                {
                    "value": state.state_code,
                    "label": state.name,
                }
                for state in _states_by_country_iso2(country_iso2)
            ),
            key=lambda state: state["label"].casefold(),
        )
    )


@lru_cache(maxsize=None)
def _cities_by_country_state(country_iso2: str, state_code: str) -> tuple:
    return tuple(get_cities_of_state(country_iso2, state_code))


@lru_cache(maxsize=None)
def _city_options_by_country_state(
    country_iso2: str, state_code: str
) -> tuple[dict[str, str], ...]:
    state_name = _state_name_by_code(country_iso2).get(state_code, state_code)
    return tuple(
        sorted(
            (
                {
                    "value": str(city.id),
                    "name": city.name,
                    "subdivision": state_name,
                    "label": city.name,
                }
                for city in _cities_by_country_state(country_iso2, state_code)
            ),
            key=lambda city: city["label"].casefold(),
        )
    )


@lru_cache(maxsize=None)
def _city_option_by_value(country_iso2: str, state_code: str) -> dict[str, dict[str, str]]:
    return {
        option["value"]: option
        for option in _city_options_by_country_state(country_iso2, state_code)
    }


@lru_cache(maxsize=None)
def _city_options_by_name(
    country_iso2: str, state_code: str
) -> dict[str, tuple[dict[str, str], ...]]:
    city_options: dict[str, list[dict[str, str]]] = {}
    for option in _city_options_by_country_state(country_iso2, state_code):
        city_options.setdefault(option["name"].casefold(), []).append(option)
    return {name: tuple(options) for name, options in city_options.items()}


def country_choices() -> list[tuple[str, str]]:
    return [("", "Select"), *[(country.name, country.name) for country in _countries()]]


def normalize_country_name(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    alias_match = _COUNTRY_ALIASES.get(normalized.casefold())
    if alias_match is not None:
        return alias_match

    return _country_name_by_casefold().get(normalized.casefold())


def country_iso2(country: str | None) -> str | None:
    normalized_country = normalize_country_name(country)
    if normalized_country is None:
        return None
    return _country_iso2_by_name().get(normalized_country)


def state_options(country: str | None) -> list[dict[str, str]]:
    country_code = country_iso2(country)
    if country_code is None:
        return []
    return [dict(option) for option in _state_options_by_country(country_code)]


def state_choice_label(value: str | None, country: str | None) -> str | None:
    country_code = country_iso2(country)
    if not value or country_code is None:
        return None

    return _state_name_by_keys(country_code).get(value.casefold(), value)


def state_choice_value(subdivision: str | None, country: str | None) -> str | None:
    country_code = country_iso2(country)
    normalized_subdivision = normalize_subdivision_name(subdivision, country)
    if country_code is None or normalized_subdivision is None:
        return None

    for state in _states_by_country_iso2(country_code):
        if state.name == normalized_subdivision:
            return state.state_code

    return None


def city_options_for_state(country: str | None, subdivision: str | None) -> list[dict[str, str]]:
    country_code = country_iso2(country)
    state_code = state_choice_value(subdivision, country)
    if country_code is None or state_code is None:
        return []
    return [dict(option) for option in _city_options_by_country_state(country_code, state_code)]


def city_choice_label(
    value: str | None, country: str | None, subdivision: str | None
) -> str | None:
    country_code = country_iso2(country)
    state_code = state_choice_value(subdivision, country)
    if not value or country_code is None or state_code is None:
        return None

    option = _city_option_by_value(country_code, state_code).get(value)
    if option is not None:
        return option["label"]

    matches = _city_options_by_name(country_code, state_code).get(value.casefold(), ())
    if len(matches) == 1:
        return matches[0]["label"]

    return value


def city_choice_value(
    city_name: str | None, country: str | None, subdivision: str | None = None
) -> str | None:
    country_code = country_iso2(country)
    state_code = state_choice_value(subdivision, country)
    if country_code is None or state_code is None or city_name is None:
        return None

    normalized_city = city_name.strip()
    if not normalized_city:
        return None

    matches = _city_options_by_name(country_code, state_code).get(normalized_city.casefold(), ())
    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]["value"]

    return matches[0]["value"]


def normalize_city_name(
    value: str | None, country: str | None, subdivision: str | None
) -> str | None:
    country_code = country_iso2(country)
    state_code = state_choice_value(subdivision, country)
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if country_code is None or state_code is None:
        return None

    option = _city_option_by_value(country_code, state_code).get(normalized)
    if option is not None:
        return option["name"]

    matches = _city_options_by_name(country_code, state_code).get(normalized.casefold(), ())
    if matches:
        return matches[0]["name"]

    return None


def normalize_subdivision_name(value: str | None, country: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    country_code = country_iso2(country)
    if country_code is None:
        return normalized

    return _state_name_by_keys(country_code).get(normalized.casefold(), normalized)
