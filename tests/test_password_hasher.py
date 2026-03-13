from unittest.mock import patch

import pytest
from flask import Flask
from passlib.hash import scrypt

from hushline.model import User
from hushline.password_hasher import LEGACY_PASSLIB_SCRYPT_PREFIX, verify_password

LEGACY_PASSLIB_SCRYPT_PASSWORD = "SecurePassword123!"
LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD = "WrongPassword123!"
LEGACY_PASSLIB_SCRYPT_SALT = b"0123456789abcdef"
LEGACY_PASSLIB_SCRYPT_COST_PREFIX = f"{LEGACY_PASSLIB_SCRYPT_PREFIX}ln=16,r=8,p=1$"


@pytest.fixture(name="legacy_passlib_scrypt_hash")
def fixture_legacy_passlib_scrypt_hash() -> str:
    return scrypt.using(salt=LEGACY_PASSLIB_SCRYPT_SALT).hash(LEGACY_PASSLIB_SCRYPT_PASSWORD)


def test_verify_password_uses_legacy_passlib_scrypt_fixture_and_logs_success(
    app: Flask, legacy_passlib_scrypt_hash: str
) -> None:
    with patch.object(app.logger, "info") as info_mock:
        assert (
            verify_password(
                LEGACY_PASSLIB_SCRYPT_PASSWORD,
                legacy_passlib_scrypt_hash,
            )
            is True
        )

    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_verification",
        "verification_result": "success",
        "hash_format": "passlib_scrypt",
        "hash_prefix": "$scrypt$",
    }
    assert "username" not in logged_extra
    assert LEGACY_PASSLIB_SCRYPT_PASSWORD not in logged_extra.values()
    assert legacy_passlib_scrypt_hash not in logged_extra.values()


def test_verify_password_rejects_wrong_password_for_legacy_passlib_scrypt_fixture(
    app: Flask, legacy_passlib_scrypt_hash: str
) -> None:
    with patch.object(app.logger, "info") as info_mock:
        assert (
            verify_password(
                LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD,
                legacy_passlib_scrypt_hash,
            )
            is False
        )

    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_verification",
        "verification_result": "failure",
        "hash_format": "passlib_scrypt",
        "hash_prefix": "$scrypt$",
    }
    assert LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD not in logged_extra.values()
    assert legacy_passlib_scrypt_hash not in logged_extra.values()


def test_legacy_passlib_scrypt_fixture_documents_prefix_and_cost_baseline(
    legacy_passlib_scrypt_hash: str,
) -> None:
    assert legacy_passlib_scrypt_hash.startswith(LEGACY_PASSLIB_SCRYPT_PREFIX)
    assert legacy_passlib_scrypt_hash.startswith(LEGACY_PASSLIB_SCRYPT_COST_PREFIX)


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
