"""First-admin initialization cannot adopt a database or reset an existing owner."""

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User
from scripts.prepare_single_tenant import INVITATION_HOURS, MARKER, prepare

ORDER = "a" * 32
CLAIM = "A" * 22


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
