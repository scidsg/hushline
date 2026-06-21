import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def _load_dev_data_module() -> ModuleType:
    script_path = ROOT / "scripts" / "dev_data.py"
    spec = importlib.util.spec_from_file_location("dev_data", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_users_include_korean_directory_account() -> None:
    dev_data = _load_dev_data_module()

    korean_george = next(
        user for user in dev_data.default_users() if user["username"] == "georgecostanzakr"
    )

    assert korean_george["display_name"] == "조지 코스탄자"
    assert korean_george["is_admin"] is False
    assert korean_george["is_verified"] is False
    assert "수축 현상" in korean_george["bio"]


def test_default_users_seed_paid_artvandelay_with_three_notification_recipients() -> None:
    dev_data = _load_dev_data_module()

    artvandelay = next(
        user for user in dev_data.default_users() if user["username"] == "artvandelay"
    )

    assert artvandelay["tier"] == "Super User"
    assert artvandelay["email"] == "artvandelay@hushline.app"
    assert artvandelay["notification_recipients"] == [
        {"email": "editor@vandelay.news", "pgp_key": dev_data.PGP_KEY, "enabled": True},
        {"email": "standards@vandelay.news", "pgp_key": dev_data.PGP_KEY, "enabled": True},
        {"email": "board@vandelay.news", "pgp_key": dev_data.PGP_KEY, "enabled": True},
    ]


def test_default_users_seed_not_newman_for_onboarding_screenshots() -> None:
    dev_data = _load_dev_data_module()
    users = dev_data.default_users()

    not_newman = next(user for user in users if user["username"] == "not_newman")

    assert all(user["username"] != "newman" for user in users)
    assert not_newman["is_verified"] is False
    assert not_newman["onboarding_complete"] is False


def test_default_users_seed_featured_verified_directory_accounts() -> None:
    dev_data = _load_dev_data_module()
    users = dev_data.default_users()

    featured_usernames = {user["username"] for user in users if user.get("is_featured") is True}
    featured_users = [user for user in users if user.get("is_featured") is True]

    assert featured_usernames == {
        "artvandelay",
        "jerryseinfeld",
        "georgecostanza",
        "elainebenes",
    }
    assert all(user["is_verified"] is True for user in featured_users)
    assert all(user["is_admin"] is False for user in featured_users)


def test_default_users_seed_more_than_twenty_verified_directory_accounts() -> None:
    dev_data = _load_dev_data_module()

    verified_usernames = [
        user["username"] for user in dev_data.default_users() if user.get("is_verified") is True
    ]

    assert len(verified_usernames) > 20
