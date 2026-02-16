import csv
import io
import zipfile
from pathlib import Path

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, User


def _read_privacy_policy() -> str:
    return Path("docs/PRIVACY.md").read_text(encoding="utf-8")


def _read_csv_from_zip(zip_file: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with zip_file.open(name) as handle:
        text = handle.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.usefixtures("_authenticated_user")
def test_ccpa_compliance_evidence_policy_and_functionality(
    client: FlaskClient, app: Flask, user: User, user2: User
) -> None:
    policy = _read_privacy_policy()
    policy_lower = policy.lower()

    # CCPA/CPRA rights language and "no sale/share" representation.
    assert "### CCPA/CPRA (California residents, where applicable)" in policy
    assert "Right to Know" in policy
    assert "Right to Delete" in policy
    assert "Right to Correct" in policy
    assert "Right to Opt-Out of Sale/Sharing of personal information" in policy
    assert "Right to Non-Discrimination" in policy
    assert "We do not sell personal information" in policy
    assert "we do not share personal information" in policy_lower
    assert "cross-context" in policy_lower

    # CCPA policy evidence should reference relevant implementation files.
    assert "hushline/settings/data_export.py" in policy
    assert "hushline/settings/delete_account.py" in policy
    assert "hushline/config.py" in policy

    # Operational privacy defaults for session/cookie handling.
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Strict"

    # Rights exercise UI is exposed for authenticated users.
    advanced_response = client.get(url_for("settings.advanced"))
    assert advanced_response.status_code == 200
    assert "Download My Data" in advanced_response.text
    assert "Delete Account" in advanced_response.text

    # Right to Know data export should not include another user's records.
    other_message = Message(username_id=user2.primary_username.id)
    db.session.add(other_message)
    db.session.commit()

    export_response = client.post(url_for("settings.data_export"), data={"encrypt_export": "false"})
    assert export_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export_response.data)) as zip_file:
        users = _read_csv_from_zip(zip_file, "db/users.csv")
        user_ids = {row.get("id") for row in users}
        assert str(user.id) in user_ids
        assert str(user2.id) not in user_ids
