import csv
import io
import zipfile
from pathlib import Path

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import AuthenticationLog, Message, User, Username, WebAuthnCredential


def _read_privacy_policy() -> str:
    return Path("docs/PRIVACY.md").read_text(encoding="utf-8")


def _read_csv_from_zip(zip_file: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with zip_file.open(name) as handle:
        text = handle.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.usefixtures("_authenticated_user")
def test_gdpr_compliance_evidence_policy_and_functionality(
    client: FlaskClient, user: User, user2: User
) -> None:
    policy = _read_privacy_policy()

    # GDPR rights language must be explicit and auditable in policy text.
    assert "### GDPR (where applicable)" in policy
    assert "Right of access" in policy
    assert "Right to rectification" in policy
    assert "Right to erasure" in policy
    assert "Right to data portability" in policy
    assert "Right to restriction or objection to processing" in policy
    assert "Right to lodge a complaint with your local data protection authority" in policy

    # Policy must point to concrete implementation files as evidence.
    assert "hushline/settings/data_export.py" in policy
    assert "hushline/settings/delete_account.py" in policy
    assert "hushline/user_deletion.py" in policy
    assert "hushline/settings/profile.py" in policy

    # Functional check: Right of access/data portability returns only current user's records.
    own_message = Message(username_id=user.primary_username.id)
    other_message = Message(username_id=user2.primary_username.id)
    user.totp_secret = "JBSWY3DPEHPK3PXP"
    user.smtp_password = "export-must-not-contain-this-password"
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=b"export-private-credential-id",
        public_key=b"export-private-public-key",
        algorithm=-7,
        sign_count=0,
        transports=[],
        device_type="single_device",
        backed_up=False,
        name="Export test key",
    )
    authentication_log = AuthenticationLog(
        user_id=user.id,
        successful=True,
        otp_code="123456",
        timecode=123,
    )
    db.session.add_all([own_message, other_message, credential, authentication_log])
    db.session.commit()

    export_response = client.post(url_for("settings.data_export"), data={"encrypt_export": "false"})
    assert export_response.status_code == 200
    assert export_response.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(export_response.data)) as zip_file:
        users = _read_csv_from_zip(zip_file, "db/users.csv")
        assert "password_hash" not in users[0]
        assert "session_id" not in users[0]
        assert "smtp_password" not in users[0]
        assert "totp_secret" not in users[0]
        user_ids = {row.get("id") for row in users}
        assert str(user.id) in user_ids
        assert str(user2.id) not in user_ids

        messages = _read_csv_from_zip(zip_file, "db/messages.csv")
        username_ids = {row.get("username_id") for row in messages}
        assert str(user.primary_username.id) in username_ids
        assert str(user2.primary_username.id) not in username_ids
        assert "db/webauthn_credentials.csv" not in zip_file.namelist()

        authentication_logs = _read_csv_from_zip(zip_file, "db/authentication_logs.csv")
        if authentication_logs:
            assert "otp_code" not in authentication_logs[0]
            assert "timecode" not in authentication_logs[0]

        archive_bytes = b"".join(zip_file.read(name) for name in zip_file.namelist())
        assert b"export-private-credential-id" not in archive_bytes
        assert b"export-private-public-key" not in archive_bytes
        assert b"export-must-not-contain-this-password" not in archive_bytes

    # Functional check: Right to erasure deletes account and related data.
    username_id = user.primary_username.id
    log = AuthenticationLog(user_id=user.id, successful=True)
    db.session.add(log)
    db.session.commit()

    delete_response = client.post(url_for("settings.delete_account"), follow_redirects=False)
    assert delete_response.status_code == 302
    assert delete_response.headers["Location"].endswith(url_for("index"))

    assert db.session.scalars(db.select(User).filter_by(id=user.id)).one_or_none() is None
    assert db.session.scalars(db.select(Username).filter_by(user_id=user.id)).first() is None
    assert db.session.scalars(db.select(Message).filter_by(username_id=username_id)).first() is None
    assert (
        db.session.scalars(db.select(AuthenticationLog).filter_by(user_id=user.id)).first() is None
    )
