from types import SimpleNamespace
from unittest.mock import patch

from hushline.model import User


def test_user_new_session_id_returns_distinct_tokens() -> None:
    first = User.new_session_id()
    second = User.new_session_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    assert first
    assert second
    assert first != second


def test_profile_location_returns_country_when_us_geography_only_has_country() -> None:
    user = User(password="SecurePassword123!")  # noqa: S106

    with patch(
        "hushline.model.user.build_directory_geography",
        return_value=SimpleNamespace(
            location="United States",
            country="United States",
            city=None,
            subdivision=None,
            subdivision_code=None,
        ),
    ):
        assert user.profile_location == "United States"


def test_profile_location_spells_out_state_when_city_missing() -> None:
    user = User(password="SecurePassword123!")  # noqa: S106
    user.country = "US"
    user.subdivision = "IL"

    assert user.profile_location == "Illinois, US"


def test_profile_location_spells_out_country_when_state_missing() -> None:
    user = User(password="SecurePassword123!")  # noqa: S106
    user.country = "US"
    user.city = "Chicago"

    assert user.profile_location == "Chicago, US"


def test_profile_location_spells_out_country_when_it_is_the_only_field() -> None:
    user = User(password="SecurePassword123!")  # noqa: S106
    user.country = "US"

    assert user.profile_location == "United States"
