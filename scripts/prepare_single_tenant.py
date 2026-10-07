"""Idempotent first-admin bootstrap confined to a new Single Tenant database."""

import hashlib
import os
import re
from datetime import UTC, datetime, timedelta

from flask import current_app
from flask_migrate import upgrade
from sqlalchemy import text

from hushline import create_app
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User

MARKER = "single_tenant_bootstrap"
INVITATION_HOURS = 24
MIGRATION_DEFAULTS = {
    OrganizationSetting.BRAND_NAME: "🤫 Hush Line",
    OrganizationSetting.BRAND_PRIMARY_COLOR: "#7d25c1",
}


def prepare(order: str, claim: str) -> None:
    db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 716340529})
    _prepare_owned(order, claim)


def _prepare_owned(order: str, claim: str, *, fresh_migration: bool = False) -> None:
    from scripts.single_tenant_live_plan import identity

    identity(order)
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}", claim):
        raise ValueError("Invalid private administrator invitation")
    limit = current_app.config.get("SINGLE_TENANT_LICENSE_LIMIT")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("Invalid paid license allowance")
    expected = {
        "order_id": order,
        "license_limit": limit,
        "claim_digest": hashlib.sha256(claim.encode()).hexdigest(),
    }
    marker = OrganizationSetting.fetch_one(MARKER)
    if marker is not None:
        if marker != expected:
            raise ValueError("Database belongs to another order or entitlement")
        # A restart never resets registration preferences, extends an invitation,
        # creates another claim or changes an administrator's existing account.
        db.session.commit()
        return
    settings = {row.key: row.value for row in db.session.scalars(db.select(OrganizationSetting))}
    if (
        db.session.scalar(db.select(db.func.count()).select_from(User))
        or db.session.scalar(db.select(db.func.count()).select_from(InviteCode))
        or (settings and not (fresh_migration and settings == MIGRATION_DEFAULTS))
    ):
        raise ValueError("Bootstrap cannot adopt an existing database")
    OrganizationSetting.upsert(MARKER, expected)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, False)
    invitation = InviteCode()
    invitation.code = claim
    invitation.expiration_date = datetime.now(UTC) + timedelta(hours=INVITATION_HOURS)
    db.session.add(invitation)
    db.session.commit()


def initialize(order: str, claim: str) -> None:
    """Attest emptiness before migration; serialize without holding migration-blocking row locks."""
    from scripts.single_tenant_live_plan import identity

    identity(order)
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}", claim):
        raise ValueError("Invalid private administrator invitation")
    with db.engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(:key)"), {"key": 716340529})
        lock.commit()
        try:
            tables = db.session.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_type='BASE TABLE'"
                )
            )
            fresh = tables == 0
            if not fresh:
                settings_table = db.session.scalar(
                    text("SELECT to_regclass('public.organization_settings')")
                )
                if settings_table is None or OrganizationSetting.fetch_one(MARKER) is None:
                    raise ValueError("Existing database has no owned Single Tenant marker")
                expected = {
                    "order_id": order,
                    "license_limit": current_app.config.get("SINGLE_TENANT_LICENSE_LIMIT"),
                    "claim_digest": hashlib.sha256(claim.encode()).hexdigest(),
                }
                if OrganizationSetting.fetch_one(MARKER) != expected:
                    raise ValueError("Database belongs to another order or entitlement")
            # Release table locks before Alembic uses its own connection. The
            # dedicated session lock still excludes another initializer.
            db.session.commit()
            upgrade()
            _prepare_owned(order, claim, fresh_migration=fresh)
        finally:
            db.session.rollback()
            try:
                lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": 716340529})
                lock.commit()
            except Exception:
                lock.invalidate()
                raise


def main() -> None:
    order = os.environ.get("SINGLE_TENANT_INSTANCE_ORDER", "")
    claim = os.environ.get("SINGLE_TENANT_ADMIN_CLAIM", "")
    if not order and not claim:
        return
    try:
        with create_app().app_context():
            initialize(order, claim)
    except Exception:
        # Database exceptions may include the private invitation as a parameter.
        raise SystemExit("Owned Single Tenant bootstrap failed; refusing to start") from None


if __name__ == "__main__":
    main()
