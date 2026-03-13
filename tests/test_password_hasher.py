from unittest.mock import patch

import pytest
from flask import Flask
from passlib.hash import scrypt
from werkzeug.security import generate_password_hash

from hushline.model import User
from hushline.password_hasher import (
    LEGACY_PASSLIB_SCRYPT_PREFIX,
    emit_password_rehash_on_auth_telemetry,
    hash_password,
    verify_password,
)

LEGACY_PASSLIB_SCRYPT_PASSWORD = "SecurePassword123!"
LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD = "WrongPassword123!"
LEGACY_PASSLIB_SCRYPT_SALT = b"0123456789abcdef"
LEGACY_PASSLIB_SCRYPT_COST_PREFIX = f"{LEGACY_PASSLIB_SCRYPT_PREFIX}ln=16,r=8,p=1$"
NATIVE_WERKZEUG_SCRYPT_PREFIX = "scrypt:"


@pytest.fixture(name="legacy_passlib_scrypt_hash")
def fixture_legacy_passlib_scrypt_hash() -> str:
    return scrypt.using(salt=LEGACY_PASSLIB_SCRYPT_SALT).hash(LEGACY_PASSLIB_SCRYPT_PASSWORD)


@pytest.fixture(name="native_werkzeug_scrypt_hash")
def fixture_native_werkzeug_scrypt_hash() -> str:
    return generate_password_hash(LEGACY_PASSLIB_SCRYPT_PASSWORD, method="scrypt")


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

    logged_extras = [call.kwargs["extra"] for call in info_mock.call_args_list]
    assert logged_extras == [
        {
            "event": "password_hash_verification",
            "verification_result": "success",
            "hash_format": "passlib_scrypt",
            "hash_prefix": "$scrypt$",
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_success_total",
            "count": 1,
            "hash_format": "passlib_scrypt",
        },
    ]
    for logged_extra in logged_extras:
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

    logged_extras = [call.kwargs["extra"] for call in info_mock.call_args_list]
    assert logged_extras == [
        {
            "event": "password_hash_verification",
            "verification_result": "failure",
            "hash_format": "passlib_scrypt",
            "hash_prefix": "$scrypt$",
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_failure_total",
            "count": 1,
            "hash_prefix": "$scrypt$",
        },
    ]
    for logged_extra in logged_extras:
        assert LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD not in logged_extra.values()
        assert legacy_passlib_scrypt_hash not in logged_extra.values()


def test_legacy_passlib_scrypt_fixture_documents_prefix_and_cost_baseline(
    legacy_passlib_scrypt_hash: str,
) -> None:
    assert legacy_passlib_scrypt_hash.startswith(LEGACY_PASSLIB_SCRYPT_PREFIX)
    assert legacy_passlib_scrypt_hash.startswith(LEGACY_PASSLIB_SCRYPT_COST_PREFIX)


def test_verify_password_uses_native_werkzeug_scrypt_hash_and_logs_success(
    app: Flask, native_werkzeug_scrypt_hash: str
) -> None:
    with patch.object(app.logger, "info") as info_mock:
        assert verify_password(LEGACY_PASSLIB_SCRYPT_PASSWORD, native_werkzeug_scrypt_hash) is True

    logged_extras = [call.kwargs["extra"] for call in info_mock.call_args_list]
    assert logged_extras == [
        {
            "event": "password_hash_verification",
            "verification_result": "success",
            "hash_format": "native_scrypt",
            "hash_prefix": NATIVE_WERKZEUG_SCRYPT_PREFIX,
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_success_total",
            "count": 1,
            "hash_format": "native_scrypt",
        },
    ]
    for logged_extra in logged_extras:
        assert LEGACY_PASSLIB_SCRYPT_PASSWORD not in logged_extra.values()
        assert native_werkzeug_scrypt_hash not in logged_extra.values()


def test_verify_password_rejects_wrong_password_for_native_werkzeug_scrypt_hash(
    app: Flask, native_werkzeug_scrypt_hash: str
) -> None:
    with patch.object(app.logger, "info") as info_mock:
        assert (
            verify_password(
                LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD,
                native_werkzeug_scrypt_hash,
            )
            is False
        )

    logged_extras = [call.kwargs["extra"] for call in info_mock.call_args_list]
    assert logged_extras == [
        {
            "event": "password_hash_verification",
            "verification_result": "failure",
            "hash_format": "native_scrypt",
            "hash_prefix": NATIVE_WERKZEUG_SCRYPT_PREFIX,
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_failure_total",
            "count": 1,
            "hash_prefix": NATIVE_WERKZEUG_SCRYPT_PREFIX,
        },
    ]
    for logged_extra in logged_extras:
        assert LEGACY_PASSLIB_SCRYPT_WRONG_PASSWORD not in logged_extra.values()
        assert native_werkzeug_scrypt_hash not in logged_extra.values()


def test_verify_password_routes_non_scrypt_native_prefixes_to_primary_verifier(
    app: Flask,
) -> None:
    stored_hash = "hl-v2:anything"
    password = "SecurePassword123!"

    with (
        patch(
            "hushline.password_hasher.verify_primary_password_hash", return_value=True
        ) as verify_mock,
        patch.object(app.logger, "info") as info_mock,
    ):
        assert verify_password(password, stored_hash) is True

    verify_mock.assert_called_once_with(password, stored_hash)
    logged_extras = [call.kwargs["extra"] for call in info_mock.call_args_list]
    assert logged_extras == [
        {
            "event": "password_hash_verification",
            "verification_result": "success",
            "hash_format": "native_hl-v2",
            "hash_prefix": "hl-v2:",
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_success_total",
            "count": 1,
            "hash_format": "native_hl-v2",
        },
    ]
    for logged_extra in logged_extras:
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
    logged_extras = [call.kwargs["extra"] for call in info_mock.call_args_list]
    assert logged_extras == [
        {
            "event": "password_hash_verification",
            "verification_result": "failure",
            "hash_format": "unknown",
            "hash_prefix": "$argon2id$",
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_failure_total",
            "count": 1,
            "hash_prefix": "$argon2id$",
        },
    ]
    for logged_extra in logged_extras:
        assert "username" not in logged_extra
        assert original_hash not in logged_extra.values()


def test_verify_password_malformed_legacy_hash_fails_closed(app: Flask) -> None:
    with patch.object(app.logger, "info") as info_mock:
        assert verify_password("SecurePassword123!", "$scrypt$") is False

    assert [call.kwargs["extra"] for call in info_mock.call_args_list] == [
        {
            "event": "password_hash_verification",
            "verification_result": "failure",
            "hash_format": "passlib_scrypt",
            "hash_prefix": "$scrypt$",
        },
        {
            "event": "password_hash_counter",
            "counter_name": "password_hash_verification_failure_total",
            "count": 1,
            "hash_prefix": "$scrypt$",
        },
    ]


def test_hash_password_logs_write_counter_without_sensitive_data(app: Flask) -> None:
    plaintext_password = "SecurePassword123!"

    with patch.object(app.logger, "info") as info_mock:
        password_hash = hash_password(plaintext_password)

    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_counter",
        "counter_name": "password_hash_write_total",
        "count": 1,
        "hash_format": "passlib_scrypt",
    }
    assert plaintext_password not in logged_extra.values()
    assert password_hash not in logged_extra.values()


@pytest.mark.parametrize(
    ("success", "counter_name"),
    [
        (True, "password_hash_rehash_on_auth_success_total"),
        (False, "password_hash_rehash_on_auth_failure_total"),
    ],
)
def test_emit_password_rehash_on_auth_telemetry_logs_counter_without_sensitive_data(
    app: Flask,
    legacy_passlib_scrypt_hash: str,
    success: bool,
    counter_name: str,
) -> None:
    with patch.object(app.logger, "info") as info_mock:
        emit_password_rehash_on_auth_telemetry(legacy_passlib_scrypt_hash, success=success)

    info_mock.assert_called_once()
    logged_extra = info_mock.call_args.kwargs["extra"]
    assert logged_extra == {
        "event": "password_hash_counter",
        "counter_name": counter_name,
        "count": 1,
        "hash_format": "passlib_scrypt",
    }
    assert legacy_passlib_scrypt_hash not in logged_extra.values()
