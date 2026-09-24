"""RFC 9980 public test vectors; never use these keys for actual disclosures."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from pysequoia import Tsk, decrypt

from hushline.crypto import (
    can_encrypt_with_pgp_key,
    encrypt_bytes,
    encrypt_message,
    is_valid_pgp_key,
)
from hushline.db import db
from hushline.model import Message, User
from hushline.settings import PGPKeyForm
from tests.helpers import form_to_data, get_profile_submission_data

VECTORS = json.loads(Path("tests/testdata/openpgp-pqc.json").read_text())["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["id"])
def test_pqc_key_validation_and_server_fallback(vector: dict[str, str]) -> None:
    public_key = vector["public_key"]
    decryptor = Tsk.from_bytes(vector["private_key"].encode()).decryptor()
    with Flask(__name__).app_context():
        assert is_valid_pgp_key(public_key)
        assert can_encrypt_with_pgp_key(public_key)
        ciphertext = encrypt_message("Synthetic PQC test: café 🔐", public_key)
        assert decrypt(ciphertext.encode(), decryptor=decryptor).bytes == (
            "Synthetic PQC test: café 🔐".encode()
        )
        binary = bytes(range(256))
        encrypted = encrypt_bytes(binary, public_key)
        assert encrypted is not None
        assert decrypt(encrypted, decryptor=decryptor).bytes == binary


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["id"])
def test_pqc_cross_library_decryption(vector: dict[str, str]) -> None:
    """Both engines must decrypt the other's output without algorithm fallback."""
    plaintext = "Synthetic cross-library PQC test: café 🔐"
    with Flask(__name__).app_context():
        server_ciphertext = encrypt_message(plaintext, vector["public_key"])
    node = shutil.which("node")
    assert node is not None, "Node is required for OpenPGP interoperability tests"
    result = subprocess.run(
        [node, "tests/pqc-interop.cjs"],  # noqa: S603 - fixed local test script, no shell
        input=json.dumps({**vector, "ciphertext": server_ciphertext, "plaintext": plaintext}),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    output = json.loads(result.stdout)
    assert output["plaintext"] == plaintext
    decryptor = Tsk.from_bytes(vector["private_key"].encode()).decryptor()
    assert decrypt(output["ciphertext"].encode(), decryptor=decryptor).bytes == plaintext.encode()


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["id"])
def test_pqc_settings_import_and_submission_without_javascript(
    vector: dict[str, str], client: FlaskClient, user: User
) -> None:
    response = client.post(
        url_for("settings.encryption"),
        data=form_to_data(PGPKeyForm(data={"pgp_key": vector["public_key"]})),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "PGP key updated successfully" in response.text
    assert user.pgp_key == vector["public_key"].strip()

    client.get(url_for("logout"))
    username = user.primary_username.username
    plaintexts = ["Synthetic PQC contact", "Synthetic PQC disclosure"]
    response = client.post(
        url_for("profile", username=username),
        data={
            **get_profile_submission_data(client, username),
            "field_0": plaintexts[0],
            "field_1": plaintexts[1],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text
    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    decryptor = Tsk.from_bytes(vector["private_key"].encode()).decryptor()
    recovered = []
    for field in message.field_values:
        assert field.value is not None
        assert "Synthetic PQC" not in field.value
        plaintext = decrypt(field.value.encode(), decryptor=decryptor).bytes
        assert plaintext is not None
        recovered.append(plaintext.decode())
    for expected in plaintexts:
        assert any(expected in plaintext for plaintext in recovered)
