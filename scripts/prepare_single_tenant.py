"""Idempotent first-admin bootstrap confined to a new Single Tenant database."""

import hashlib
import os
import re
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import text

from hushline import create_app
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User

MARKER = "single_tenant_bootstrap"
INVITATION_HOURS = 24


def prepare(order: str, claim: str) -> None:
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
    db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 716340529})
    marker = OrganizationSetting.fetch_one(MARKER)
    if marker is not None:
        if marker != expected:
            raise ValueError("Database belongs to another order or entitlement")
        # A restart never resets registration preferences, extends an invitation,
        # creates another claim or changes an administrator's existing account.
        db.session.commit()
        return
    if (
        db.session.scalar(db.select(db.func.count()).select_from(User))
        or db.session.scalar(db.select(db.func.count()).select_from(InviteCode))
        or db.session.scalar(db.select(db.func.count()).select_from(OrganizationSetting))
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


def main() -> None:
    order = os.environ.get("SINGLE_TENANT_INSTANCE_ORDER", "")
    claim = os.environ.get("SINGLE_TENANT_ADMIN_CLAIM", "")
    if not order and not claim:
        return
    try:
        with create_app().app_context():
            prepare(order, claim)
    except Exception:
        # Database exceptions may include the private invitation as a parameter.
        raise SystemExit("Owned Single Tenant bootstrap failed; refusing to start") from None


if __name__ == "__main__":
    main()
