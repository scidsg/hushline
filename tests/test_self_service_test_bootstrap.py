"""The isolated test bootstrap cannot open registration or overwrite an admin."""

from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User
import scripts.prepare_self_service_test as bootstrap
from scripts.prepare_self_service_test import prepare

CLAIM = "A" * 22
TEST_PASSWORD = "made-up-only-password"


def test_invitation_is_private_short_lived_and_idempotent(app: Flask) -> None:
    with app.app_context():
        prepare("hushline-staging-pr-99999", CLAIM)
        prepare("hushline-staging-pr-99999", CLAIM)
        codes = db.session.scalars(db.select(InviteCode)).all()
        assert len(codes) == 1
        assert codes[0].code == CLAIM
        assert (
            datetime.now(timezone.utc)
            < codes[0].expiration_date.replace(tzinfo=timezone.utc)
            <= datetime.now(timezone.utc) + timedelta(hours=1)
        )
        assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_CODES_REQUIRED)
        assert not OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED)


def test_bootstrap_rejects_shared_workspace(app: Flask) -> None:
    with app.app_context(), pytest.raises(ValueError, match="isolated staging"):
        prepare("hushline-infra", CLAIM)


def test_bootstrap_rejects_bad_claim(app: Flask) -> None:
    with app.app_context(), pytest.raises(ValueError, match="invitation format"):
        prepare("hushline-staging-pr-99999", "bad")


def test_bootstrap_leaves_existing_user_untouched(app: Flask) -> None:
    with app.app_context():
        user = User(password=TEST_PASSWORD)
        user.is_admin = True
        db.session.add(user)
        db.session.commit()
        prepare("hushline-staging-pr-99999", CLAIM)
        assert db.session.scalar(db.select(db.func.count()).select_from(InviteCode)) == 0
        assert user.is_admin


def test_bootstrap_failure_does_not_expose_invitation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELF_SERVICE_TEST_WORKSPACE", "hushline-staging-pr-99999")
    monkeypatch.setenv("SELF_SERVICE_TEST_CLAIM_CODE", CLAIM)

    def failed_app() -> Flask:
        raise RuntimeError(CLAIM)

    monkeypatch.setattr(bootstrap, "create_app", failed_app)
    with pytest.raises(SystemExit, match="Private test bootstrap failed") as error:
        bootstrap.main()
    assert CLAIM not in str(error.value)
    assert error.value.__suppress_context__
