import csv
import io
import zipfile

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import FieldValue, Message, User


def _read_csv_from_zip(zip_file: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with zip_file.open(name) as handle:
        text = handle.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _pgp_message_names(zip_file: zipfile.ZipFile) -> list[str]:
    return [name for name in zip_file.namelist() if name.startswith("pgp_messages/")]


@pytest.mark.usefixtures("_authenticated_user")
def test_data_export_requires_auth(client: FlaskClient) -> None:
    client.get(url_for("logout"))
    response = client.get(url_for("settings.data_export"))
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_data_export_zip_contains_csv_and_pgp(
    client: FlaskClient, user: User
) -> None:
    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.commit()

    field_def = user.primary_username.message_fields[-1]
    field_value = FieldValue(field_def, message, "secret message", True)
    db.session.add(field_value)
    db.session.commit()

    response = client.get(url_for("settings.data_export"))
    assert response.status_code == 200
    assert response.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.data)) as zip_file:
        names = zip_file.namelist()
        assert "db/users.csv" in names
        assert "db/usernames.csv" in names
        assert "db/messages.csv" in names
        assert "db/field_definitions.csv" in names
        assert "db/field_values.csv" in names

        pgp_files = _pgp_message_names(zip_file)
        assert pgp_files
        content = zip_file.read(pgp_files[0]).decode("utf-8")
        assert content.startswith("-----BEGIN PGP MESSAGE-----")


@pytest.mark.usefixtures("_authenticated_user")
def test_data_export_only_includes_current_user(
    client: FlaskClient, user: User, user2: User
) -> None:
    message = Message(username_id=user2.primary_username.id)
    db.session.add(message)
    db.session.commit()

    response = client.get(url_for("settings.data_export"))
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.data)) as zip_file:
        usernames = _read_csv_from_zip(zip_file, "db/usernames.csv")
        usernames_set = {row.get("username") for row in usernames}
        assert user.primary_username.username in usernames_set
        assert user2.primary_username.username not in usernames_set
