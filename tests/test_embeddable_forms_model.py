import pytest

from hushline.db import db
from hushline.model import OrganizationSetting, StripeSubscriptionStatusEnum, User, Username
from hushline.model.username import normalize_embed_origin


def _enable_embeds_globally() -> None:
    OrganizationSetting.upsert(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED, True)


def _add_pgp_key(user: User) -> None:
    with open("tests/test_pgp_key.txt") as file:
        user.pgp_key = file.read().strip()


def _make_current_paid_super_user(user: User) -> None:
    user.set_business_tier()
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.ACTIVE


def _make_message_capable(user: User) -> None:
    _make_current_paid_super_user(user)
    _add_pgp_key(user)


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


def test_embed_requires_current_paid_super_user(user: User) -> None:
    _enable_embeds_globally()
    _add_pgp_key(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is False

    user.set_business_tier()
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.INCOMPLETE
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is False

    user.stripe_subscription_status = StripeSubscriptionStatusEnum.ACTIVE
    db.session.commit()

    assert user.primary_username.embed_allows_origin("https://tips.example") is True


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
        "http://tips.example;.onion",
        "http://tips.example .onion",
        "http://tips.example\t.onion",
        "http://tips.example\n.onion",
        "http://tips.example\f.onion",
        "http://tips.example\r.onion",
    ],
)
def test_embed_allowed_origins_reject_invalid_origin_rules(user: User, origin: str) -> None:
    with pytest.raises(ValueError, match="Embed origins"):
        user.primary_username.set_embed_allowed_origins([origin])


def test_embed_origin_normalization_canonicalizes_host_and_ports() -> None:
    assert normalize_embed_origin("https://Tips.Example:8443") == "https://tips.example:8443"
    assert normalize_embed_origin("https://Tips.Example:443") == "https://tips.example"
    assert normalize_embed_origin("http://localhost:80") == "http://localhost"
    assert normalize_embed_origin("http://127.0.0.2:80") == "http://127.0.0.2"
    assert normalize_embed_origin("http://exampleonion.onion:80") == "http://exampleonion.onion"


@pytest.mark.parametrize(
    ("configured_origin", "browser_origin", "stored_origin"),
    [
        ("https://Tips.Example:443", "https://tips.example", "https://tips.example"),
        ("http://localhost:80", "http://localhost", "http://localhost"),
        ("http://127.0.0.2:80", "http://127.0.0.2", "http://127.0.0.2"),
    ],
)
def test_embed_default_port_allowlist_matches_browser_serialized_origin(
    user: User, configured_origin: str, browser_origin: str, stored_origin: str
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user.primary_username, configured_origin)
    db.session.commit()

    assert user.primary_username.embed_allowed_origins == [stored_origin]
    assert user.primary_username.embed_allows_origin(browser_origin) is True


def test_embed_rejects_non_exception_http_origins() -> None:
    with pytest.raises(ValueError, match="must use https"):
        normalize_embed_origin("http://tips.example")


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
    _make_current_paid_super_user(user)
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
