from unittest.mock import patch

import pytest
from flask import Flask
from passlib.hash import scrypt

from hushline.model import User
from hushline.password_hasher import verify_password


def test_verify_password_uses_legacy_passlib_scrypt_and_logs_success(app: Flask) -> None:
    password = "SecurePassword123!"
    stored_hash = scrypt.hash(password)

    with patch.object(app.logger, "info") as info_mock:
        assert verify_password(password, stored_hash) is True

    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_verification",
        "verification_result": "success",
        "hash_format": "passlib_scrypt",
        "hash_prefix": "$scrypt$",
    }
    assert "username" not in logged_extra
    assert password not in logged_extra.values()
    assert stored_hash not in logged_extra.values()


@pytest.mark.parametrize(
    ("stored_hash", "expected_format"),
    [
        ("scrypt:anything", "native_scrypt"),
        ("hl-v2:anything", "native_hl-v2"),
    ],
)
def test_verify_password_routes_native_prefixes_to_primary_verifier(
    app: Flask, stored_hash: str, expected_format: str
) -> None:
    password = "SecurePassword123!"

    with (
        patch(
            "hushline.password_hasher.verify_primary_password_hash", return_value=True
        ) as verify_mock,
        patch.object(app.logger, "info") as info_mock,
    ):
        assert verify_password(password, stored_hash) is True

    verify_mock.assert_called_once_with(password, stored_hash)
    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_verification",
        "verification_result": "success",
        "hash_format": expected_format,
        "hash_prefix": stored_hash.split(":", 1)[0] + ":",
    }
    assert password not in logged_extra.values()
    assert stored_hash not in logged_extra.values()


def test_verify_password_unknown_prefix_fails_closed_without_mutating_user(
    app: Flask, user: User
) -> None:
    user._password_hash = "$argon2id$pretend-hash-value"
    original_hash = user.password_hash

    with (
        patch("hushline.password_hasher.verify_primary_password_hash") as verify_mock,
        patch.object(app.logger, "info") as info_mock,
    ):
        assert user.check_password("SecurePassword123!") is False

    assert user.password_hash == original_hash
    verify_mock.assert_not_called()
    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_verification",
        "verification_result": "failure",
        "hash_format": "unknown",
        "hash_prefix": "$argon2id$",
    }
    assert "username" not in logged_extra
    assert original_hash not in logged_extra.values()


def test_verify_password_malformed_legacy_hash_fails_closed(app: Flask) -> None:
    with patch.object(app.logger, "info") as info_mock:
        assert verify_password("SecurePassword123!", "$scrypt$") is False

    info_mock.assert_called_once()
    assert info_mock.call_args.kwargs["extra"] == {
        "event": "password_hash_verification",
        "verification_result": "failure",
        "hash_format": "passlib_scrypt",
        "hash_prefix": "$scrypt$",
    }
