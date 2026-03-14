import pytest

from hushline.model.directory_listing_geography import (
    DirectoryListingGeography,
    build_directory_geography,
    build_public_record_geography,
)


@pytest.mark.parametrize(
    ("subdivision_input", "expected_subdivision", "expected_code"),
    [
        ("IL", "Illinois", "IL"),
        ("Illinois", "Illinois", "IL"),
    ],
)
def test_build_directory_geography_normalizes_us_subdivision_codes(
    subdivision_input: str, expected_subdivision: str, expected_code: str
) -> None:
    geography = build_directory_geography(
        country="United States",
        subdivision=subdivision_input,
    )

    assert geography.country == "United States"
    assert geography.subdivision == expected_subdivision
    assert geography.subdivision_code == expected_code
    assert geography.countries == ("United States",)


@pytest.mark.parametrize(
    ("geography", "expected_location"),
    [
        (DirectoryListingGeography(subdivision="Illinois"), "Illinois"),
        (
            DirectoryListingGeography(subdivision="Illinois", country="United States"),
            "Illinois, United States",
        ),
        (DirectoryListingGeography(country="Australia"), "Australia"),
        (
            DirectoryListingGeography(countries=("All countries", "USA")),
            "All countries, USA",
        ),
    ],
)
def test_directory_listing_geography_location_variants(
    geography: DirectoryListingGeography, expected_location: str
) -> None:
    assert geography.location == expected_location


def test_build_public_record_geography_uses_state_as_subdivision_when_country_present() -> None:
    geography = build_public_record_geography(
        city="Los Angeles",
        state="California",
        country="United States",
    )

    assert geography.city == "Los Angeles"
    assert geography.country == "United States"
    assert geography.subdivision == "California"
    assert geography.subdivision_code == "CA"
    assert geography.countries == ("United States",)
    assert geography.location == "Los Angeles, California, United States"


def test_build_public_record_geography_uses_us_state_code_when_country_missing() -> None:
    geography = build_public_record_geography(
        city="Chicago",
        state="IL",
    )

    assert geography.city == "Chicago"
    assert geography.country == "United States"
    assert geography.subdivision == "Illinois"
    assert geography.subdivision_code == "IL"


def test_build_public_record_geography_uses_non_us_state_value_as_country_when_missing() -> None:
    geography = build_public_record_geography(
        city="Paris",
        state="France",
    )

    assert geography.city == "Paris"
    assert geography.country == "France"
    assert geography.subdivision is None
    assert geography.subdivision_code is None


def test_build_directory_geography_keeps_non_us_subdivision_strings() -> None:
    geography = build_directory_geography(
        country="France",
        subdivision="Ile-de-France",
    )

    assert geography.country == "France"
    assert geography.subdivision == "Ile-de-France"
    assert geography.subdivision_code == "Ile-de-France"
