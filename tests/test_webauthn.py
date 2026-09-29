import base64
import copy
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from flask import Flask
from pytest_mock import MockFixture
from sqlalchemy.exc import IntegrityError
from webauthn.helpers.exceptions import InvalidAuthenticationResponse

from hushline.auth import clear_auth_session
from hushline.db import db
from hushline.model import User, WebAuthnChallenge, WebAuthnCredential, WebAuthnUserHandle
from hushline.settings.data_export import _fetch_rows
from hushline.webauthn import (
    WebAuthnCeremonyService,
    WebAuthnChallengeError,
    WebAuthnChallengeService,
    WebAuthnConfigurationError,
    WebAuthnPurpose,
    WebAuthnRateLimitError,
    WebAuthnVerificationError,
    _persist_authentication_result,
    _session_binding_hash,
    current_webauthn_session_binding,
)

FIXTURE_PATH = Path(__file__).parent / "testdata" / "webauthn-ceremonies.json"
SESSION_BINDING = "session-binding-that-is-long-enough-for-webauthn"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _decode(value: str) -> bytes:
    encoded = value.encode("ascii")
    return base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))


def _configure(app: Flask) -> None:
    app.config.update(
        WEBAUTHN_RP_ID="localhost",
        WEBAUTHN_ORIGIN="http://localhost:5000",
        WEBAUTHN_RP_NAME="Hush Line Test",
    )


def _store_fixture_challenge(
    *, user: User, challenge: bytes, purpose: WebAuthnPurpose, expired: bool = False
) -> None:
    now = datetime.now(UTC)
    db.session.add(
        WebAuthnChallenge(
            user_id=user.id,
            purpose=purpose.value,
            challenge_hash=sha256(challenge).digest(),
            session_binding_hash=_session_binding_hash(SESSION_BINDING),
            created_at=now - timedelta(minutes=10) if expired else now,
            expires_at=now - timedelta(seconds=1) if expired else now + timedelta(minutes=5),
        )
    )
    db.session.commit()


def _registration_fixture() -> tuple[bytes, dict[str, object]]:
    fixture = _fixture()["registration"]
    assert isinstance(fixture, dict)
    challenge = fixture["challenge"]
    response = fixture["response"]
    assert isinstance(challenge, str)
    assert isinstance(response, dict)
    return _decode(challenge), response


def _authentication_fixture() -> tuple[bytes, bytes, dict[str, object]]:
    fixture = _fixture()["authentication"]
    assert isinstance(fixture, dict)
    challenge = fixture["challenge"]
    public_key = fixture["credential_public_key"]
    response = fixture["response"]
    assert isinstance(challenge, str)
    assert isinstance(public_key, str)
    assert isinstance(response, dict)
    return _decode(challenge), _decode(public_key), response


def test_configuration_is_explicit_and_does_not_trust_request_host(app: Flask, user: User) -> None:
    app.config.pop("WEBAUTHN_RP_ID", None)
    app.config.pop("WEBAUTHN_ORIGIN", None)
    with (
        app.test_request_context(headers={"Host": "attacker.example"}),
        pytest.raises(WebAuthnConfigurationError),
    ):
        WebAuthnCeremonyService.begin_registration(
            user=user,
            username=user.primary_username.username,
            display_name=None,
            session_binding=SESSION_BINDING,
        )


def test_registration_options_are_private_bounded_and_account_specific(
    app: Flask, user: User
) -> None:
    _configure(app)

    options = WebAuthnCeremonyService.begin_registration(
        user=user,
        username=user.primary_username.username,
        display_name="Test User",
        session_binding=SESSION_BINDING,
    )

    assert options["rp"] == {"id": "localhost", "name": "Hush Line Test"}
    assert options["attestation"] == "none"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["user"]["id"] != str(user.id)
    assert len(_decode(options["user"]["id"])) == WebAuthnUserHandle.HANDLE_LENGTH
    assert {item["alg"] for item in options["pubKeyCredParams"]} == {-8, -7, -257}
    stored = db.session.scalar(
        db.select(WebAuthnChallenge).where(WebAuthnChallenge.user_id == user.id)
    )
    assert stored is not None
    assert stored.challenge_hash == sha256(_decode(options["challenge"])).digest()


def test_registration_fixture_verifies_and_stores_only_operational_metadata(
    app: Flask, user: User
) -> None:
    _configure(app)
    challenge, response = _registration_fixture()
    user.webauthn_user_handle = WebAuthnUserHandle()
    db.session.commit()
    _store_fixture_challenge(
        user=user,
        challenge=challenge,
        purpose=WebAuthnPurpose.REGISTRATION,
    )

    credential = WebAuthnCeremonyService.finish_registration(
        user=user,
        session_binding=SESSION_BINDING,
        response=response,
        name="Office key",
    )

    assert credential.algorithm == -257
    assert credential.sign_count == 0
    assert credential.transports == ["internal"]
    assert credential.name == "Office key"
    raw_id = response["rawId"]
    assert isinstance(raw_id, str)
    assert credential.credential_id == _decode(raw_id)
    assert "webauthn_credentials" not in _fetch_rows(user.id)


@pytest.mark.parametrize(
    ("rp_id", "origin"),
    [
        ("localhost", "http://localhost:5001"),
        ("example.com", "https://example.com"),
    ],
)
def test_registration_rejects_wrong_origin_or_rp(
    app: Flask, user: User, rp_id: str, origin: str
) -> None:
    _configure(app)
    app.config.update(WEBAUTHN_RP_ID=rp_id, WEBAUTHN_ORIGIN=origin)
    challenge, response = _registration_fixture()
    user.webauthn_user_handle = WebAuthnUserHandle()
    db.session.commit()
    _store_fixture_challenge(
        user=user,
        challenge=challenge,
        purpose=WebAuthnPurpose.REGISTRATION,
    )

    with pytest.raises(WebAuthnVerificationError):
        WebAuthnCeremonyService.finish_registration(
            user=user,
            session_binding=SESSION_BINDING,
            response=response,
        )


def test_registration_rejects_unsupported_public_key_algorithm(app: Flask, user: User) -> None:
    _configure(app)
    challenge, original_response = _registration_fixture()
    response = copy.deepcopy(original_response)
    response_data = response["response"]
    assert isinstance(response_data, dict)
    attestation = _decode(response_data["attestationObject"])
    supported_rs256 = b"\xa4\x01\x03\x03\x39\x01\x00"
    unsupported_rs384 = b"\xa4\x01\x03\x03\x39\x01\x01"
    assert supported_rs256 in attestation
    response_data["attestationObject"] = (
        base64.urlsafe_b64encode(attestation.replace(supported_rs256, unsupported_rs384, 1))
        .rstrip(b"=")
        .decode("ascii")
    )
    user.webauthn_user_handle = WebAuthnUserHandle()
    db.session.commit()
    _store_fixture_challenge(
        user=user,
        challenge=challenge,
        purpose=WebAuthnPurpose.REGISTRATION,
    )

    with pytest.raises(WebAuthnVerificationError):
        WebAuthnCeremonyService.finish_registration(
            user=user,
            session_binding=SESSION_BINDING,
            response=response,
        )


def test_malformed_registration_is_rejected_without_logging_payload(
    app: Flask, user: User, caplog: pytest.LogCaptureFixture
) -> None:
    _configure(app)

    with pytest.raises(WebAuthnVerificationError) as error:
        WebAuthnCeremonyService.finish_registration(
            user=user,
            session_binding=SESSION_BINDING,
            response={"rawId": "secret-credential-value", "response": {}},
        )

    assert "secret-credential-value" not in str(error.value)
    assert error.value.__cause__ is None
    assert "secret-credential-value" not in caplog.text

    with pytest.raises(WebAuthnVerificationError, match="Malformed WebAuthn response"):
        WebAuthnCeremonyService.finish_registration(
            user=user,
            session_binding=SESSION_BINDING,
            response="[" * 1100 + "]" * 1100,
        )


def test_registration_rejects_binary_fields_that_decode_over_the_limit(
    app: Flask, user: User
) -> None:
    _configure(app)
    oversized_challenge = base64.urlsafe_b64encode(b"c" * 129).decode("ascii")
    client_data = base64.urlsafe_b64encode(
        json.dumps({"challenge": oversized_challenge}).encode("utf-8")
    ).decode("ascii")

    with pytest.raises(WebAuthnVerificationError, match="Malformed challenge"):
        WebAuthnCeremonyService.finish_registration(
            user=user,
            session_binding=SESSION_BINDING,
            response={"response": {"clientDataJSON": client_data}},
        )

    app.config["WEBAUTHN_MAX_RESPONSE_BYTES"] = 128
    with pytest.raises(WebAuthnVerificationError, match="too large"):
        WebAuthnCeremonyService.finish_registration(
            user=user,
            session_binding=SESSION_BINDING,
            response={"padding": "x" * 256},
        )


def test_challenge_is_bound_to_account_purpose_session_and_single_use(
    app: Flask, user: User, user2: User
) -> None:
    _configure(app)
    challenge = WebAuthnChallengeService.issue(
        user_id=user.id,
        purpose=WebAuthnPurpose.AUTHENTICATION,
        session_binding=SESSION_BINDING,
    )

    rejected = [
        (user2.id, WebAuthnPurpose.AUTHENTICATION, SESSION_BINDING),
        (user.id, WebAuthnPurpose.RECOVERY, SESSION_BINDING),
        (user.id, WebAuthnPurpose.AUTHENTICATION, "different-session-binding-that-is-long-enough"),
    ]
    for user_id, purpose, binding in rejected:
        with pytest.raises(WebAuthnChallengeError):
            WebAuthnChallengeService.consume(
                challenge=challenge,
                user_id=user_id,
                purpose=purpose,
                session_binding=binding,
            )

    WebAuthnChallengeService.consume(
        challenge=challenge,
        user_id=user.id,
        purpose=WebAuthnPurpose.AUTHENTICATION,
        session_binding=SESSION_BINDING,
    )
    with pytest.raises(WebAuthnChallengeError):
        WebAuthnChallengeService.consume(
            challenge=challenge,
            user_id=user.id,
            purpose=WebAuthnPurpose.AUTHENTICATION,
            session_binding=SESSION_BINDING,
        )


def test_auth_session_rotation_invalidates_challenge_binding(app: Flask, user: User) -> None:
    _configure(app)
    with app.test_request_context():
        initial_binding = current_webauthn_session_binding()
        challenge = WebAuthnChallengeService.issue(
            user_id=user.id,
            purpose=WebAuthnPurpose.AUTHENTICATION,
            session_binding=initial_binding,
        )
        assert current_webauthn_session_binding() == initial_binding

        clear_auth_session()
        rotated_binding = current_webauthn_session_binding()
        assert rotated_binding != initial_binding
        with pytest.raises(WebAuthnChallengeError):
            WebAuthnChallengeService.consume(
                challenge=challenge,
                user_id=user.id,
                purpose=WebAuthnPurpose.AUTHENTICATION,
                session_binding=rotated_binding,
            )


def test_stale_challenge_and_issue_rate_limits_are_enforced(app: Flask, user: User) -> None:
    _configure(app)
    app.config.update(
        WEBAUTHN_RATE_LIMIT_ACCOUNT_MAX=1,
        WEBAUTHN_RATE_LIMIT_SESSION_MAX=1,
    )
    stale = b"s" * 64
    _store_fixture_challenge(
        user=user,
        challenge=stale,
        purpose=WebAuthnPurpose.RECOVERY,
        expired=True,
    )
    with pytest.raises(WebAuthnChallengeError):
        WebAuthnChallengeService.consume(
            challenge=stale,
            user_id=user.id,
            purpose=WebAuthnPurpose.RECOVERY,
            session_binding=SESSION_BINDING,
        )

    WebAuthnChallengeService.issue(
        user_id=user.id,
        purpose=WebAuthnPurpose.AUTHENTICATION,
        session_binding=SESSION_BINDING,
    )
    with pytest.raises(WebAuthnRateLimitError):
        WebAuthnChallengeService.issue(
            user_id=user.id,
            purpose=WebAuthnPurpose.AUTHENTICATION,
            session_binding=SESSION_BINDING,
        )


def test_authentication_options_require_user_verification_and_limit_credentials(
    app: Flask, user: User
) -> None:
    _configure(app)
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=b"authentication-options-key",
        public_key=b"public-key",
        algorithm=-7,
        sign_count=0,
        transports=["usb"],
        device_type="single_device",
        backed_up=False,
    )
    db.session.add(credential)
    db.session.commit()

    options = WebAuthnCeremonyService.begin_authentication(
        user=user,
        session_binding=SESSION_BINDING,
    )

    assert options["userVerification"] == "required"
    assert [_decode(item["id"]) for item in options["allowCredentials"]] == [
        credential.credential_id
    ]


def test_authentication_fixture_verifies_signature_user_handle_and_counter(
    app: Flask, user: User
) -> None:
    _configure(app)
    challenge, public_key, response = _authentication_fixture()
    response = copy.deepcopy(response)
    response_data = response["response"]
    assert isinstance(response_data, dict)
    user_handle = b"u" * WebAuthnUserHandle.HANDLE_LENGTH
    response_data["userHandle"] = base64.urlsafe_b64encode(user_handle).rstrip(b"=").decode("ascii")
    user.webauthn_user_handle = WebAuthnUserHandle(handle=user_handle)
    raw_id = response["rawId"]
    assert isinstance(raw_id, str)
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=_decode(raw_id),
        public_key=public_key,
        algorithm=-257,
        sign_count=0,
        transports=["usb"],
        device_type="single_device",
        backed_up=False,
    )
    db.session.add(credential)
    db.session.commit()
    _store_fixture_challenge(
        user=user,
        challenge=challenge,
        purpose=WebAuthnPurpose.AUTHENTICATION,
    )

    verified = WebAuthnCeremonyService.finish_authentication(
        user=user,
        session_binding=SESSION_BINDING,
        response=response,
    )

    assert verified.id == credential.id
    assert verified.sign_count == 1
    assert verified.last_used_at is not None


def test_authentication_rejects_a_credential_owned_by_another_account(
    app: Flask, user: User, user2: User
) -> None:
    _configure(app)
    db.session.add(
        WebAuthnCredential(
            user_id=user.id,
            credential_id=b"credential-id",
            public_key=b"public-key",
            algorithm=-7,
            sign_count=0,
            transports=[],
            device_type="single_device",
            backed_up=False,
        )
    )
    db.session.commit()
    challenge = b"d" * 64
    _store_fixture_challenge(
        user=user2,
        challenge=challenge,
        purpose=WebAuthnPurpose.AUTHENTICATION,
    )

    with pytest.raises(WebAuthnVerificationError):
        WebAuthnCeremonyService.finish_authentication(
            user=user2,
            session_binding=SESSION_BINDING,
            response=_minimal_authentication_response(challenge),
        )

    stored_challenge = db.session.scalar(
        db.select(WebAuthnChallenge).where(WebAuthnChallenge.user_id == user2.id)
    )
    assert stored_challenge is not None
    assert stored_challenge.consumed_at is not None


def test_zero_counter_authenticator_is_allowed_and_counter_replay_is_rejected(
    app: Flask, user: User, mocker: MockFixture
) -> None:
    _configure(app)
    user.webauthn_user_handle = WebAuthnUserHandle(handle=b"u" * 64)
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=b"credential-id",
        public_key=b"public-key",
        algorithm=-7,
        sign_count=0,
        transports=[],
        device_type="single_device",
        backed_up=False,
    )
    db.session.add(credential)
    db.session.commit()

    class Verification:
        credential_id = b"credential-id"
        new_sign_count = 0
        credential_device_type = type("DeviceType", (), {"value": "single_device"})()
        credential_backed_up = False

    mocker.patch("hushline.webauthn.verify_authentication_response", return_value=Verification())
    for marker in (b"a", b"b"):
        challenge = marker * 64
        _store_fixture_challenge(
            user=user,
            challenge=challenge,
            purpose=WebAuthnPurpose.AUTHENTICATION,
        )
        response = _minimal_authentication_response(challenge)
        verified = WebAuthnCeremonyService.finish_authentication(
            user=user,
            session_binding=SESSION_BINDING,
            response=response,
        )
        assert verified.sign_count == 0

    challenge = b"c" * 64
    _store_fixture_challenge(
        user=user,
        challenge=challenge,
        purpose=WebAuthnPurpose.AUTHENTICATION,
    )
    mocker.patch(
        "hushline.webauthn.verify_authentication_response",
        side_effect=InvalidAuthenticationResponse("counter did not increase"),
    )
    with pytest.raises(WebAuthnVerificationError):
        WebAuthnCeremonyService.finish_authentication(
            user=user,
            session_binding=SESSION_BINDING,
            response=_minimal_authentication_response(challenge),
        )


def test_counter_update_rejects_concurrent_use_but_allows_zero_counters(
    app: Flask, user: User
) -> None:
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=b"concurrent-counter",
        public_key=b"public-key",
        algorithm=-7,
        sign_count=1,
        transports=[],
        device_type="single_device",
        backed_up=False,
    )
    zero_counter = WebAuthnCredential(
        user_id=user.id,
        credential_id=b"zero-counter",
        public_key=b"public-key",
        algorithm=-7,
        sign_count=0,
        transports=[],
        device_type="single_device",
        backed_up=False,
    )
    db.session.add_all((credential, zero_counter))
    db.session.commit()

    _persist_authentication_result(
        credential,
        expected_sign_count=1,
        new_sign_count=2,
        device_type="single_device",
        backed_up=False,
    )
    with pytest.raises(WebAuthnVerificationError, match="concurrently"):
        _persist_authentication_result(
            credential,
            expected_sign_count=1,
            new_sign_count=2,
            device_type="single_device",
            backed_up=False,
        )

    _persist_authentication_result(
        zero_counter,
        expected_sign_count=0,
        new_sign_count=0,
        device_type="single_device",
        backed_up=False,
    )
    _persist_authentication_result(
        zero_counter,
        expected_sign_count=0,
        new_sign_count=0,
        device_type="single_device",
        backed_up=False,
    )

    db.session.execute(
        db.update(WebAuthnCredential)
        .where(WebAuthnCredential.id == zero_counter.id)
        .values(disabled_at=datetime.now(UTC))
    )
    db.session.commit()
    with pytest.raises(WebAuthnVerificationError, match="concurrently"):
        _persist_authentication_result(
            zero_counter,
            expected_sign_count=0,
            new_sign_count=0,
            device_type="single_device",
            backed_up=False,
        )


def _minimal_authentication_response(challenge: bytes) -> dict[str, object]:
    client_data = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "type": "webauthn.get",
                    "challenge": base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii"),
                    "origin": "http://localhost:5000",
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    credential_id = base64.urlsafe_b64encode(b"credential-id").rstrip(b"=").decode("ascii")
    return {
        "id": credential_id,
        "rawId": credential_id,
        "type": "public-key",
        "response": {"clientDataJSON": client_data},
    }


def test_credential_identity_and_ownership_constraints(app: Flask, user: User, user2: User) -> None:
    handle = WebAuthnUserHandle(user_id=user.id, handle=b"h" * 64)
    db.session.add(handle)
    db.session.commit()
    db.session.add(WebAuthnUserHandle(user_id=user2.id, handle=b"h" * 64))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    db.session.add(
        WebAuthnCredential(
            user_id=user.id,
            credential_id=b"same-id",
            public_key=b"key",
            algorithm=-7,
            sign_count=0,
            transports=[],
            device_type="single_device",
            backed_up=False,
        )
    )
    db.session.commit()
    db.session.add(
        WebAuthnCredential(
            user_id=user2.id,
            credential_id=b"same-id",
            public_key=b"other-key",
            algorithm=-7,
            sign_count=0,
            transports=[],
            device_type="single_device",
            backed_up=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
