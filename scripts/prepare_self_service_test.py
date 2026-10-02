"""Prepare a private, one-use admin invitation for an isolated self-service test."""

import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from hushline import create_app
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User


def prepare(workspace: str, claim_code: str) -> None:
    if not re.fullmatch(r"hushline-staging-pr-[1-9][0-9]*", workspace):
        raise ValueError("Only an isolated staging workspace can bootstrap a test invitation")
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}", claim_code):
        raise ValueError("Invalid test invitation format")
    # Multiple app instances share this new database; serialize bootstrap writes.
    db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 716340528})
    if db.session.scalar(db.select(db.func.count()).select_from(User)):
        db.session.commit()
        return
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, False)
    existing = db.session.scalar(db.select(InviteCode).where(InviteCode.code == claim_code))
    if existing is None:
        invitation = InviteCode()
        invitation.code = claim_code
        invitation.expiration_date = datetime.now(timezone.utc) + timedelta(hours=1)
        db.session.add(invitation)
    db.session.commit()


def main() -> None:
    workspace = os.environ.get("SELF_SERVICE_TEST_WORKSPACE", "")
    claim_code = os.environ.get("SELF_SERVICE_TEST_CLAIM_CODE", "")
    if not claim_code:
        return
    with create_app().app_context():
        prepare(workspace, claim_code)


if __name__ == "__main__":
    main()
