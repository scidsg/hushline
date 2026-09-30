import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.auth import CHAT_KEY_SESSION_ID_SESSION_KEY
from hushline.chat_key_lifecycle import (
    PQ_CHAT_ARCHIVE_SUITE,
    PQ_CHAT_PROTOCOL,
    canonical_chat_json,
    invalidate_pq_account_after_password_reset,
)
from hushline.db import db
from hushline.model import (
    ChatAccount,
    ChatArchiveEpoch,
    ChatDevice,
    ChatKey,
    ChatOneTimePrekey,
    ChatPqRateLimitAttempt,
    ChatPrekeyClaim,
    ChatSignedPrekey,
    User,
)
from hushline.routes.pq_device import (
    MEMBERSHIP_SIGNATURE_DOMAIN,
    PREKEY_SIGNATURE_DOMAIN,
    REVOCATION_SIGNATURE_DOMAIN,
    UNLOCK_SIGNATURE_DOMAIN,
)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sign_ed25519(key: Ed25519PrivateKey, domain: bytes, value: Any) -> str:
    return _b64url(key.sign(domain + b"\x00" + canonical_chat_json(value)))


def _sign_p256(key: ec.EllipticCurvePrivateKey, domain: bytes, value: Any) -> str:
    der = key.sign(domain + b"\x00" + canonical_chat_json(value), ec.ECDSA(hashes.SHA256()))
    r_value, s_value = decode_dss_signature(der)
    return _b64url(r_value.to_bytes(32, "big") + s_value.to_bytes(32, "big"))


def _authenticate(client: FlaskClient, user: User, chat_session_id: str) -> None:
    with client.session_transaction() as browser_session:
        browser_session["user_id"] = user.id
        browser_session["session_id"] = user.session_id
        browser_session["username"] = user.primary_username.username
        browser_session["is_authenticated"] = True
        browser_session[CHAT_KEY_SESSION_ID_SESSION_KEY] = chat_session_id


def _add_unlock_key(user: User) -> ec.EllipticCurvePrivateKey:
    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.public_key().public_numbers()
    public_jwk = {
        "crv": "P-256",
        "key_ops": ["verify"],
        "kty": "EC",
        "x": _b64url(numbers.x.to_bytes(32, "big")),
        "y": _b64url(numbers.y.to_bytes(32, "big")),
    }
    user.chat_keys.append(
        ChatKey(
            key_version=1,
            public_key='{"crv":"P-256","kty":"EC","x":"x","y":"y"}',
            public_signing_key=json.dumps(public_jwk),
            encrypted_private_key="wrapped",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"hash": "SHA-256", "iterations": 310000},
            kdf_salt=_b64url(b"s" * 16),
            wrapping_algorithm="AES-GCM",
            recovery_state="available",
        )
    )
    db.session.commit()
    return key


def _enroll(  # noqa: PLR0913
    client: FlaskClient,
    user: User,
    *,
    chat_session_id: str,
    device_id: str | None = None,
    account_key: Ed25519PrivateKey | None = None,
    device_key: Ed25519PrivateKey | None = None,
    unlock_key: ec.EllipticCurvePrivateKey | None = None,
    signed_prekey_id: int = 101,
    one_time_prekey_start: int = 1,
    expected_status: int = 201,
) -> dict[str, Any]:
    _authenticate(client, user, chat_session_id)
    unlock_key = unlock_key or _add_unlock_key(user)
    account_key = account_key or Ed25519PrivateKey.generate()
    device_key = device_key or Ed25519PrivateKey.generate()
    account_public_key = _b64url(
        account_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    device_public_key = _b64url(
        device_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    resolved_device_id = device_id or str(uuid4())
    bootstrap = client.post(url_for("pq_account_bootstrap"))
    assert bootstrap.status_code == 200
    account_state = bootstrap.get_json()
    archive_public_key = b"a" * 1216
    now = datetime.now(UTC).replace(microsecond=0)
    membership = {
        "account_id": account_state["account_id"],
        "archive_epoch": 1,
        "archive_public_key_sha256": hashlib.sha256(archive_public_key).hexdigest(),
        "archive_suites": [PQ_CHAT_ARCHIVE_SUITE],
        "capabilities": [PQ_CHAT_PROTOCOL],
        "device_id": resolved_device_id,
        "device_signing_public_key": device_public_key,
        "expires_at": _timestamp(now + timedelta(days=30)),
        "identity_version": 1,
        "issued_at": _timestamp(now),
        "membership_sequence": account_state["membership_sequence"] + 1,
        "one_time_prekey_end": one_time_prekey_start + 99,
        "one_time_prekey_start": one_time_prekey_start,
        "protocol_identity_public_key": _b64url(
            b"\x05" + hashlib.sha256(resolved_device_id.encode()).digest()
        ),
        "protocol_registration_id": (
            int.from_bytes(hashlib.sha256(resolved_device_id.encode()).digest()[:2], "big") % 16_380
            + 1
        ),
        "signed_prekey_id": signed_prekey_id,
        "status": "active",
    }
    payload = {
        "account_identity_public_key": account_public_key,
        "archive": {
            "encrypted_private_key": _b64url(b"encrypted-archive-key"),
            "epoch": 1,
            "public_key": _b64url(archive_public_key),
        },
        "membership": membership,
        "membership_signature": _sign_ed25519(account_key, MEMBERSHIP_SIGNATURE_DOMAIN, membership),
    }
    payload["unlock_signature"] = _sign_p256(
        unlock_key,
        UNLOCK_SIGNATURE_DOMAIN,
        {
            "account_identity_public_key": account_public_key,
            "membership": membership,
        },
    )
    response = client.post(url_for("pq_enroll_device"), json=payload)
    assert response.status_code == expected_status
    return {
        "account_id": account_state["account_id"],
        "account_key": account_key,
        "device_id": membership["device_id"],
        "device_key": device_key,
        "membership": membership,
        "payload": payload,
        "response": response,
        "session_id": chat_session_id,
        "unlock_key": unlock_key,
    }


def _prekey_proof(enrollment: dict[str, Any], kind: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": enrollment["device_id"],
        "key": value,
        "kind": kind,
        "membership_sequence": enrollment["membership"]["membership_sequence"],
        "protocol": PQ_CHAT_PROTOCOL,
    }


def _publish(
    client: FlaskClient,
    user: User,
    enrollment: dict[str, Any],
    *,
    key_ids: tuple[int, ...] = (1,),
    classical_key_type: int = 0x05,
) -> Any:
    _authenticate(client, user, enrollment["session_id"])
    issued_at = datetime.fromisoformat(enrollment["membership"]["issued_at"].replace("Z", "+00:00"))
    signed_prekey = {
        "classical_public_key": _b64url(bytes([classical_key_type]) + b"s" * 32),
        "classical_signature": _b64url(b"c" * 64),
        "expires_at": _timestamp(issued_at + timedelta(days=7)),
        "key_id": enrollment["membership"]["signed_prekey_id"],
        "pq_public_key": _b64url(b"\x08" + b"q" * 1568),
        "pq_signature": _b64url(b"r" * 64),
    }
    signed_prekey["device_signature"] = _sign_ed25519(
        enrollment["device_key"],
        PREKEY_SIGNATURE_DOMAIN,
        _prekey_proof(enrollment, "signed", signed_prekey),
    )
    one_time_prekeys = []
    for key_id in key_ids:
        value = {
            "classical_public_key": _b64url(bytes([classical_key_type]) + bytes([key_id]) * 32),
            "expires_at": enrollment["membership"]["expires_at"],
            "key_id": key_id,
            "pq_public_key": _b64url(b"\x08" + bytes([key_id + 1]) * 1568),
            "pq_signature": _b64url(bytes([key_id + 2]) * 64),
        }
        value["device_signature"] = _sign_ed25519(
            enrollment["device_key"],
            PREKEY_SIGNATURE_DOMAIN,
            _prekey_proof(enrollment, "one-time", value),
        )
        one_time_prekeys.append(value)
    publication = {
        "device_id": enrollment["device_id"],
        "membership_sequence": enrollment["membership"]["membership_sequence"],
        "one_time_prekeys": one_time_prekeys,
        "protocol": PQ_CHAT_PROTOCOL,
        "signed_prekey": signed_prekey,
    }
    return client.post(
        url_for("pq_publish_prekeys", device_id=enrollment["device_id"]),
        json={
            "publication": publication,
            "signature": _sign_ed25519(
                enrollment["device_key"], PREKEY_SIGNATURE_DOMAIN, publication
            ),
        },
    )


def _claim(
    client: FlaskClient,
    claimant: User,
    claimant_enrollment: dict[str, Any],
    target_enrollment: dict[str, Any],
    claim_id: str,
) -> Any:
    _authenticate(client, claimant, claimant_enrollment["session_id"])
    return client.post(
        url_for(
            "pq_claim_prekey",
            account_id=target_enrollment["account_id"],
            device_id=target_enrollment["device_id"],
        ),
        headers={"X-Hushline-Device-ID": claimant_enrollment["device_id"]},
        json={"claim_id": claim_id},
    )


def test_enrollment_requires_unlock_and_account_signatures(client: FlaskClient, user: User) -> None:
    enrollment = _enroll(client, user, chat_session_id="enrollment-session")

    listing = client.get(
        url_for("pq_account_devices", account_id=enrollment["account_id"]),
        headers={"X-Hushline-Device-ID": enrollment["device_id"]},
    )

    assert listing.status_code == 200
    assert "no-store" in listing.headers["Cache-Control"]
    assert "private" in listing.headers["Cache-Control"]
    assert "script-src 'self'" in listing.headers["Content-Security-Policy"]
    assert "'unsafe-eval'" not in listing.headers["Content-Security-Policy"]
    body = listing.get_json()
    assert body["membership_sequence"] == 1
    assert body["devices"] == [
        {
            "membership": enrollment["membership"],
            "membership_sha256": hashlib.sha256(
                canonical_chat_json(enrollment["membership"])
            ).hexdigest(),
            "membership_signature": enrollment["payload"]["membership_signature"],
        }
    ]
    assert "ip_address" not in listing.text
    assert "fingerprint" not in listing.text
    assert "label" not in listing.text


def test_enrollment_rejects_forgery_and_replays_identical_request(
    client: FlaskClient, user: User
) -> None:
    enrollment = _enroll(client, user, chat_session_id="valid-session")
    forged = enrollment["payload"] | {
        "membership": enrollment["membership"]
        | {"device_id": str(uuid4()), "membership_sequence": 2}
    }

    forged_response = client.post(url_for("pq_enroll_device"), json=forged)
    replay_response = client.post(url_for("pq_enroll_device"), json=enrollment["payload"])

    assert forged_response.status_code == 403
    assert forged_response.get_json() == {"error": "AUTHENTICATION_FAILED"}
    assert replay_response.status_code == 200
    assert replay_response.get_json()["device"]["membership"] == enrollment["membership"]


def test_new_enrollment_keeps_existing_authenticated_browser_active(
    client: FlaskClient, user: User
) -> None:
    first = _enroll(client, user, chat_session_id="first-browser")
    second = _enroll(
        client,
        user,
        chat_session_id="second-browser",
        account_key=first["account_key"],
        unlock_key=first["unlock_key"],
    )

    _authenticate(client, user, first["session_id"])
    listing = client.get(
        url_for("pq_account_devices", account_id=first["account_id"]),
        headers={"X-Hushline-Device-ID": first["device_id"]},
    )

    assert listing.status_code == 200
    assert listing.get_json()["membership_sequence"] == 2
    listed_device_ids = {
        device["membership"]["device_id"] for device in listing.get_json()["devices"]
    }
    assert listed_device_ids == {
        first["device_id"],
        second["device_id"],
    }
    assert _publish(client, user, first).status_code == 201


def test_enrollment_rejects_device_identity_reuse(client: FlaskClient, user: User) -> None:
    first = _enroll(client, user, chat_session_id="identity-first")

    duplicate = _enroll(
        client,
        user,
        chat_session_id="identity-duplicate",
        account_key=first["account_key"],
        device_key=first["device_key"],
        unlock_key=first["unlock_key"],
        expected_status=409,
    )

    assert duplicate["response"].get_json() == {"error": "STATE_CONFLICT"}


def test_prekey_publication_is_authenticated_idempotent_and_replenishable(
    client: FlaskClient, user: User
) -> None:
    enrollment = _enroll(client, user, chat_session_id="publisher-session")

    first = _publish(client, user, enrollment, key_ids=(1, 2))
    retry = _publish(client, user, enrollment, key_ids=(1, 2))
    replenishment = _publish(client, user, enrollment, key_ids=(3,))

    assert first.status_code == 201
    assert first.get_json()["created"] == 2
    assert retry.status_code == 201
    assert retry.get_json()["created"] == 0
    assert replenishment.status_code == 201
    assert replenishment.get_json() == {
        "available": 3,
        "created": 1,
        "replenish_below": 20,
        "target": 100,
    }


def test_membership_renewal_rotates_prekey_ranges_without_reuse(
    client: FlaskClient, user: User, user2: User
) -> None:
    first = _enroll(client, user, chat_session_id="rotation-recipient")
    assert _publish(client, user, first, key_ids=(1, 2)).status_code == 201

    renewed = _enroll(
        client,
        user,
        chat_session_id=first["session_id"],
        device_id=first["device_id"],
        account_key=first["account_key"],
        device_key=first["device_key"],
        unlock_key=first["unlock_key"],
        signed_prekey_id=202,
        one_time_prekey_start=101,
    )
    assert _publish(client, user, renewed, key_ids=(101, 102)).status_code == 201
    claimant = _enroll(client, user2, chat_session_id="rotation-sender")
    claimed = _claim(client, user2, claimant, renewed, str(uuid4()))

    assert claimed.status_code == 201
    assert claimed.get_json()["signed_prekey"]["key_id"] == 202
    assert claimed.get_json()["one_time_prekey"]["key_id"] == 101
    old_signed_prekey = db.session.scalars(
        db.select(ChatSignedPrekey).where(ChatSignedPrekey.key_id == 101)
    ).one()
    old_one_time_prekeys = list(
        db.session.scalars(db.select(ChatOneTimePrekey).where(ChatOneTimePrekey.key_id.in_((1, 2))))
    )
    assert old_signed_prekey.retired_at is not None
    assert old_one_time_prekeys == []


def test_prekey_publication_rejects_signed_suite_substitution(
    client: FlaskClient, user: User
) -> None:
    enrollment = _enroll(client, user, chat_session_id="suite-substitution")

    response = _publish(client, user, enrollment, classical_key_type=0x04)

    assert response.status_code == 400
    assert response.get_json() == {"error": "SUITE_MISMATCH"}
    assert db.session.scalar(db.select(db.func.count()).select_from(ChatOneTimePrekey)) == 0


def test_concurrent_claims_never_return_the_same_one_time_prekey(
    app: Flask, client: FlaskClient, user: User, user2: User
) -> None:
    claimant = _enroll(client, user, chat_session_id="claimant-session")
    target = _enroll(client, user2, chat_session_id="target-session")
    assert _publish(client, user2, target).status_code == 201
    endpoint = url_for(
        "pq_claim_prekey",
        account_id=target["account_id"],
        device_id=target["device_id"],
    )
    user_id = user.id
    user_session_id = user.session_id
    username = user.primary_username.username

    def claim() -> tuple[int, dict[str, Any]]:
        with app.test_client() as concurrent_client:
            with concurrent_client.session_transaction() as browser_session:
                browser_session["user_id"] = user_id
                browser_session["session_id"] = user_session_id
                browser_session["username"] = username
                browser_session["is_authenticated"] = True
                browser_session[CHAT_KEY_SESSION_ID_SESSION_KEY] = claimant["session_id"]
            response = concurrent_client.post(
                endpoint,
                headers={"X-Hushline-Device-ID": claimant["device_id"]},
                json={"claim_id": str(uuid4())},
            )
            return response.status_code, response.get_json()

    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in (executor.submit(claim), executor.submit(claim))]

    assert sorted(status for status, _ in results) == [201, 409]
    success = next(body for status, body in results if status == 201)
    failure = next(body for status, body in results if status == 409)
    assert success["one_time_prekey"]["key_id"] == 1
    assert failure == {"error": "PREKEY_DEPLETED"}


def test_consumed_claim_leaves_tombstone_and_replay_fails_closed(
    client: FlaskClient, user: User, user2: User
) -> None:
    claimant = _enroll(client, user, chat_session_id="consumer-session")
    target = _enroll(client, user2, chat_session_id="offline-session")
    assert _publish(client, user2, target).status_code == 201
    _authenticate(client, user, claimant["session_id"])
    unauthorized = client.post(
        url_for(
            "pq_claim_prekey",
            account_id=target["account_id"],
            device_id=target["device_id"],
        ),
        headers={"X-Hushline-Device-ID": str(uuid4())},
        json={"claim_id": str(uuid4())},
    )
    assert unauthorized.status_code == 409
    assert unauthorized.get_json() == {"error": "STALE_MEMBERSHIP"}
    claim_id = str(uuid4())
    claimed = _claim(client, user, claimant, target, claim_id)
    assert claimed.status_code == 201

    consumed = client.post(
        url_for("pq_consume_prekey_claim", claim_id=claim_id),
        headers={"X-Hushline-Device-ID": claimant["device_id"]},
    )
    replay = _claim(client, user, claimant, target, claim_id)

    assert consumed.status_code == 200
    assert replay.status_code == 409
    assert replay.get_json() == {"error": "PREKEY_REPLAY"}
    claim_tombstone = db.session.scalars(
        db.select(ChatPrekeyClaim).where(ChatPrekeyClaim.claim_id == claim_id)
    ).one()
    tombstone = claim_tombstone.prekey
    assert claim_tombstone.consumed_at is not None
    assert tombstone.consumed_at is not None
    assert tombstone.tombstone_expires_at is not None


def test_expired_reservation_releases_prekey_without_forgetting_old_claim(
    client: FlaskClient, user: User, user2: User
) -> None:
    claimant = _enroll(client, user, chat_session_id="reservation-sender")
    target = _enroll(client, user2, chat_session_id="reservation-recipient")
    assert _publish(client, user2, target).status_code == 201
    old_claim_id = str(uuid4())
    first = _claim(client, user, claimant, target, old_claim_id)
    assert first.status_code == 201
    old_claim = db.session.scalars(
        db.select(ChatPrekeyClaim).where(ChatPrekeyClaim.claim_id == old_claim_id)
    ).one()
    old_claim.reservation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.session.commit()

    replacement = _claim(client, user, claimant, target, str(uuid4()))
    replay = _claim(client, user, claimant, target, old_claim_id)

    assert replacement.status_code == 201
    assert replacement.get_json()["one_time_prekey"]["key_id"] == 1
    assert replay.status_code == 409
    assert replay.get_json() == {"error": "STATE_CONFLICT"}


def test_cleanup_retains_then_expires_claim_tombstones(
    client: FlaskClient, user: User, user2: User
) -> None:
    claimant = _enroll(client, user, chat_session_id="cleanup-sender")
    target = _enroll(client, user2, chat_session_id="cleanup-recipient")
    assert _publish(client, user2, target).status_code == 201
    claim_id = str(uuid4())
    assert _claim(client, user, claimant, target, claim_id).status_code == 201
    claim = db.session.scalars(
        db.select(ChatPrekeyClaim).where(ChatPrekeyClaim.claim_id == claim_id)
    ).one()
    claim.reservation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    claim.prekey.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.session.commit()

    retained = _claim(client, user, claimant, target, claim_id)

    assert retained.status_code == 409
    retained_claim = db.session.scalars(
        db.select(ChatPrekeyClaim).where(ChatPrekeyClaim.claim_id == claim_id)
    ).one_or_none()
    assert retained_claim is not None
    retained_claim.tombstone_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.session.commit()
    _enroll(
        client,
        user,
        chat_session_id="cleanup-second-browser",
        account_key=claimant["account_key"],
        unlock_key=claimant["unlock_key"],
    )
    depleted = _claim(client, user, claimant, target, str(uuid4()))

    assert depleted.status_code == 409
    assert depleted.get_json() == {"error": "PREKEY_DEPLETED"}
    forgotten_claim = db.session.scalars(
        db.select(ChatPrekeyClaim).where(ChatPrekeyClaim.claim_id == claim_id)
    ).one_or_none()
    assert forgotten_claim is None


def test_expired_and_revoked_device_supply_is_never_claimed(
    client: FlaskClient, user: User, user2: User
) -> None:
    claimant = _enroll(client, user, chat_session_id="sender-session")
    target = _enroll(client, user2, chat_session_id="recipient-session")
    assert _publish(client, user2, target, key_ids=(1, 2)).status_code == 201
    first_prekey = db.session.scalars(
        db.select(ChatOneTimePrekey).where(ChatOneTimePrekey.key_id == 1)
    ).one()
    first_prekey.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.session.commit()

    claim = _claim(client, user, claimant, target, str(uuid4()))
    assert claim.status_code == 201
    assert claim.get_json()["one_time_prekey"]["key_id"] == 2

    _authenticate(client, user2, target["session_id"])
    now = datetime.now(UTC).replace(microsecond=0)
    revocation = {
        "account_id": target["account_id"],
        "device_id": target["device_id"],
        "membership_sequence": target["membership"]["membership_sequence"] + 1,
        "revoked_at": _timestamp(now),
        "status": "revoked",
    }
    revoked = client.post(
        url_for("pq_revoke_device", device_id=target["device_id"]),
        json={
            "revocation": revocation,
            "signature": _sign_ed25519(
                target["account_key"], REVOCATION_SIGNATURE_DOMAIN, revocation
            ),
        },
    )
    denied = _claim(client, user, claimant, target, str(uuid4()))

    assert revoked.status_code == 200
    assert denied.status_code == 409
    assert denied.get_json() == {"error": "STALE_MEMBERSHIP"}


def test_revocation_race_never_leaves_a_consumable_claim(
    app: Flask, client: FlaskClient, user: User, user2: User
) -> None:
    claimant = _enroll(client, user, chat_session_id="race-claimant")
    target = _enroll(client, user2, chat_session_id="race-target")
    assert _publish(client, user2, target).status_code == 201
    claim_id = str(uuid4())
    claim_endpoint = url_for(
        "pq_claim_prekey",
        account_id=target["account_id"],
        device_id=target["device_id"],
    )
    revoke_endpoint = url_for("pq_revoke_device", device_id=target["device_id"])
    now = datetime.now(UTC).replace(microsecond=0)
    revocation = {
        "account_id": target["account_id"],
        "device_id": target["device_id"],
        "membership_sequence": 2,
        "revoked_at": _timestamp(now),
        "status": "revoked",
    }
    revocation_payload = {
        "revocation": revocation,
        "signature": _sign_ed25519(target["account_key"], REVOCATION_SIGNATURE_DOMAIN, revocation),
    }
    claimant_auth = (
        user.id,
        str(user.session_id),
        user.primary_username.username,
        claimant["session_id"],
    )
    target_auth = (
        user2.id,
        str(user2.session_id),
        user2.primary_username.username,
        target["session_id"],
    )

    def authenticate_concurrent(
        concurrent_client: FlaskClient, auth: tuple[int, str, str, str]
    ) -> None:
        with concurrent_client.session_transaction() as browser_session:
            browser_session["user_id"] = auth[0]
            browser_session["session_id"] = auth[1]
            browser_session["username"] = auth[2]
            browser_session["is_authenticated"] = True
            browser_session[CHAT_KEY_SESSION_ID_SESSION_KEY] = auth[3]

    def claim() -> int:
        with app.test_client() as concurrent_client:
            authenticate_concurrent(concurrent_client, claimant_auth)
            return concurrent_client.post(
                claim_endpoint,
                headers={"X-Hushline-Device-ID": claimant["device_id"]},
                json={"claim_id": claim_id},
            ).status_code

    def revoke() -> int:
        with app.test_client() as concurrent_client:
            authenticate_concurrent(concurrent_client, target_auth)
            return concurrent_client.post(revoke_endpoint, json=revocation_payload).status_code

    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as executor:
        claim_future = executor.submit(claim)
        revoke_future = executor.submit(revoke)
        claim_status = claim_future.result()
        revoke_status = revoke_future.result()

    assert revoke_status == 200
    assert claim_status in {201, 409}
    if claim_status == 201:
        authenticate_concurrent(client, claimant_auth)
        consumed = client.post(
            url_for("pq_consume_prekey_claim", claim_id=claim_id),
            headers={"X-Hushline-Device-ID": claimant["device_id"]},
        )
        assert consumed.status_code == 409
        assert consumed.get_json() == {"error": "STATE_CONFLICT"}


def test_device_operation_rate_limits_are_separate_and_persistent(
    app: Flask, client: FlaskClient, user: User, user2: User
) -> None:
    app.config["PQ_PREKEY_CLAIM_RATE_LIMIT_MAX"] = 1
    claimant = _enroll(client, user, chat_session_id="limited-claimant")
    target = _enroll(client, user2, chat_session_id="limited-target")
    assert _publish(client, user2, target, key_ids=(1, 2)).status_code == 201

    first = _claim(client, user, claimant, target, str(uuid4()))
    second = _claim(client, user, claimant, target, str(uuid4()))

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.get_json() == {"error": "RATE_LIMITED"}
    actions = db.session.scalars(
        db.select(ChatPqRateLimitAttempt.action).where(ChatPqRateLimitAttempt.user_id == user.id)
    ).all()
    assert actions.count("device_create") == 1
    assert actions.count("prekey_claim") == 1


def test_device_creation_and_publication_have_independent_limits(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["PQ_DEVICE_CREATION_RATE_LIMIT_MAX"] = 1
    app.config["PQ_PREKEY_PUBLICATION_RATE_LIMIT_MAX"] = 1
    enrolled = _enroll(client, user, chat_session_id="operation-limit-first")
    blocked_enrollment = _enroll(
        client,
        user,
        chat_session_id="operation-limit-second",
        account_key=enrolled["account_key"],
        unlock_key=enrolled["unlock_key"],
        expected_status=429,
    )

    assert blocked_enrollment["response"].get_json() == {"error": "RATE_LIMITED"}
    assert _publish(client, user, enrolled, key_ids=(1,)).status_code == 201
    blocked_publication = _publish(client, user, enrolled, key_ids=(2,))

    assert blocked_publication.status_code == 429
    assert blocked_publication.get_json() == {"error": "RATE_LIMITED"}
    published_key_ids = set(db.session.scalars(db.select(ChatOneTimePrekey.key_id)).all())
    assert published_key_ids == {1}


def test_password_reset_invalidates_identity_devices_prekeys_and_archive(
    client: FlaskClient, user: User
) -> None:
    enrollment = _enroll(client, user, chat_session_id="reset-session")
    assert _publish(client, user, enrollment).status_code == 201
    reset_at = datetime.now(UTC)

    invalidate_pq_account_after_password_reset(user, when=reset_at)
    db.session.commit()

    account = db.session.scalars(db.select(ChatAccount).where(ChatAccount.user_id == user.id)).one()
    device = db.session.scalars(
        db.select(ChatDevice).where(ChatDevice.account_id == account.id)
    ).one()
    prekey = db.session.scalars(db.select(ChatOneTimePrekey)).one()
    epoch = db.session.scalars(db.select(ChatArchiveEpoch)).one()
    assert account.identity_public_key is None
    assert account.identity_version == 2
    assert account.membership_sequence == 2
    assert device.revoked_at is not None
    assert prekey.expires_at == reset_at
    assert epoch.retired_at == reset_at
