import pytest

from hushline.db import db
from hushline.model import OrganizationSetting, User, Username
from hushline.model.username import normalize_embed_origin


def _enable_embeds_globally() -> None:
    OrganizationSetting.upsert(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED, True)


def _make_message_capable(user: User) -> None:
    with open("tests/test_pgp_key.txt") as file:
        user.pgp_key = file.read().strip()


def _configure_embed(username: Username, origin: str = "https://tips.example") -> None:
    username.embed_enabled = True
    username.set_embed_allowed_origins([origin])


def test_global_embed_enablement_defaults_disabled(user: User) -> None:
    _make_message_capable(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    assert OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED) is False
    assert user.primary_username.embed_allows_origin("https://tips.example") is False


def test_primary_profile_requires_opt_in_and_exact_allowed_origin(user: User) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    user.primary_username.set_embed_allowed_origins(["https://tips.example"])
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is False

    user.primary_username.embed_enabled = True
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is True
    assert user.primary_username.embed_allows_origin("https://other.example") is False
    assert user.primary_username.embed_allows_origin("https://tips.example/path") is False


def test_alias_embed_opt_in_is_independent_from_primary_profile(
    user: User, user_alias: Username
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user.primary_username, "https://primary.example")
    user_alias.set_embed_allowed_origins(["https://alias.example"])
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://primary.example") is True
    assert user_alias.embed_allows_origin("https://alias.example") is False

    user.primary_username.embed_enabled = False
    user_alias.embed_enabled = True
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://primary.example") is False
    assert user_alias.embed_allows_origin("https://alias.example") is True
    assert user_alias.embed_allows_origin("https://primary.example") is False


@pytest.mark.parametrize(
    "origin",
    [
        "",
        " https://tips.example",
        "*",
        "https://*.example",
        "ftp://tips.example",
        "https://tips.example/path",
        "https://tips.example?campaign=1",
        "https://tips.example#fragment",
        "https://user:pass@tips.example",
        "https://tips.example:",
    ],
)
def test_embed_allowed_origins_reject_invalid_origin_rules(user: User, origin: str) -> None:
    with pytest.raises(ValueError, match="Embed origins"):
        user.primary_username.set_embed_allowed_origins([origin])


def test_embed_origin_normalization_preserves_exact_host_and_port() -> None:
    assert normalize_embed_origin("https://Tips.Example:8443") == "https://tips.example:8443"


def test_embed_requires_at_least_one_exact_allowed_origin(user: User) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    user.primary_username.embed_enabled = True
    db.session.commit()

    assert not user.primary_username.embed_allowed_origins
    assert user.primary_username.embed_allows_origin("https://tips.example") is False


def test_embed_admin_disablement_blocks_profile(user: User) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user.primary_username)
    user.primary_username.embed_admin_disabled = True
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is False


def test_embed_preserves_missing_key_and_suspension_rejection(user: User) -> None:
    _enable_embeds_globally()
    _configure_embed(user.primary_username)
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is False

    _make_message_capable(user)
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is True

    user.is_suspended = True
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is False


def test_alias_embed_requires_owner_eligibility(user: User, user_alias: Username) -> None:
    _enable_embeds_globally()
    _configure_embed(user_alias, "https://alias.example")
    db.session.commit()

    assert user_alias.embed_allows_origin("https://alias.example") is False

    _make_message_capable(user)
    db.session.commit()

    assert user_alias.embed_allows_origin("https://alias.example") is True

    user.is_suspended = True
    db.session.commit()

    assert user_alias.embed_allows_origin("https://alias.example") is False
