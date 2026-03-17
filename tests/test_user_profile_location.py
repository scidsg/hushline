from hushline.model import User


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
