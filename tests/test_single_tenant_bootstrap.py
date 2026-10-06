"""First-admin initialization cannot adopt a database or reset an existing owner."""

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from pytest_mock import MockFixture
from sqlalchemy import text

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User
from scripts.prepare_single_tenant import (
    INVITATION_HOURS,
    MARKER,
    MIGRATION_DEFAULTS,
    initialize,
    prepare,
)

ORDER = "a" * 32
CLAIM = "A" * 22


@pytest.fixture(autouse=True)
def _fresh_unit_settings(app: Flask) -> None:
    # Both schema creation modes describe the same unconfigured unit database.
    # These rows belong only to this temporary test database, never an instance.
    rows = list(db.session.scalars(db.select(OrganizationSetting)))
    values = {row.key: row.value for row in rows}
    assert values in ({}, MIGRATION_DEFAULTS)
    for row in rows:
        db.session.delete(row)
    db.session.commit()


def test_new_database_records_paid_entitlement_and_private_invitation(app: Flask) -> None:
    app.config["SINGLE_TENANT_LICENSE_LIMIT"] = 25
    prepare(ORDER, CLAIM)
    marker = OrganizationSetting.fetch_one(MARKER)
    assert marker["order_id"] == ORDER
    assert marker["license_limit"] == 25
    assert CLAIM not in str(marker)
    invitation = db.session.scalar(db.select(InviteCode))
    assert invitation is not None
    expiry = invitation.expiration_date
    prepare(ORDER, CLAIM)
    assert db.session.scalar(db.select(db.func.count()).select_from(InviteCode)) == 1
    assert invitation.expiration_date == expiry
    assert expiry.replace(tzinfo=UTC) <= datetime.now(UTC) + timedelta(hours=INVITATION_HOURS)
    assert not OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED)


def test_unlimited_is_explicitly_recorded_and_not_a_finite_default(app: Flask) -> None:
    app.config.pop("SINGLE_TENANT_LICENSE_LIMIT", None)
    prepare(ORDER, CLAIM)
    assert OrganizationSetting.fetch_one(MARKER)["license_limit"] is None


def test_existing_unowned_database_cannot_be_adopted(app: Flask, user: User) -> None:
    with pytest.raises(ValueError, match="cannot adopt"):
        prepare(ORDER, CLAIM)
    assert OrganizationSetting.fetch_one(MARKER) is None
    assert user.id is not None


def test_another_order_or_changed_allowance_cannot_reset_database(app: Flask) -> None:
    app.config["SINGLE_TENANT_LICENSE_LIMIT"] = 2
    prepare(ORDER, CLAIM)
    with pytest.raises(ValueError, match="another order"):
        prepare("b" * 32, CLAIM)
    db.session.rollback()
    app.config["SINGLE_TENANT_LICENSE_LIMIT"] = 3
    with pytest.raises(ValueError, match="entitlement"):
        prepare(ORDER, CLAIM)
    db.session.rollback()
    assert OrganizationSetting.fetch_one(MARKER)["license_limit"] == 2


def test_restart_preserves_admin_and_changed_registration_preferences(app: Flask) -> None:
    prepare(ORDER, CLAIM)
    user = User(password="unit-test-only-not-a-real-password")  # noqa: S106 — fake test password
    user.is_admin = True
    db.session.add(user)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    db.session.commit()
    prepare(ORDER, CLAIM)
    assert user.is_admin
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED)


def test_seeded_defaults_alone_never_authorize_adoption(app: Flask) -> None:
    for key, value in MIGRATION_DEFAULTS.items():
        OrganizationSetting.upsert(key, value)
    db.session.commit()
    with pytest.raises(ValueError, match="cannot adopt"):
        prepare(ORDER, CLAIM)
    db.session.rollback()
    with pytest.raises(ValueError, match="no owned"):
        initialize(ORDER, CLAIM)
    assert OrganizationSetting.fetch_one(MARKER) is None


def test_real_empty_database_is_migrated_before_owned_bootstrap(app: Flask) -> None:
    # This is an isolated disposable pytest database; there is no provider access.
    db.session.commit()
    db.drop_all()
    db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
    db.session.commit()
    initialize(ORDER, CLAIM)
    assert OrganizationSetting.fetch_one(MARKER)["order_id"] == ORDER
    assert (
        OrganizationSetting.fetch_one(OrganizationSetting.BRAND_NAME)
        == MIGRATION_DEFAULTS[OrganizationSetting.BRAND_NAME]
    )
    invitation = db.session.scalar(db.select(InviteCode))
    assert invitation is not None
    expiry = invitation.expiration_date
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    db.session.commit()
    initialize(ORDER, CLAIM)
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED)
    invitation = db.session.scalar(db.select(InviteCode))
    assert invitation is not None
    assert invitation.expiration_date == expiry


def test_existing_owned_restart_does_not_block_schema_migrations(
    app: Flask, mocker: MockFixture
) -> None:
    prepare(ORDER, CLAIM)

    def migration() -> None:
        with db.engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout='1s'"))
            connection.execute(
                text("ALTER TABLE organization_settings ADD COLUMN migration_test integer")
            )

    mocker.patch("scripts.prepare_single_tenant.upgrade", side_effect=migration)
    initialize(ORDER, CLAIM)
    assert OrganizationSetting.fetch_one(MARKER)["order_id"] == ORDER
