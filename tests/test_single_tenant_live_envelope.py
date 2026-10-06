"""Invitations remain private and a different order cannot decrypt results."""

import json

import pytest

from scripts.single_tenant_live_envelope import MAX_PRIVATE_BYTES, decrypt, encrypt, keys


def test_only_owned_key_can_read_invitation() -> None:
    private, public = keys()
    other, _ = keys()
    value = {"claim_code": "private-claim-only-in-test", "state": "awaiting_dns"}
    envelope = encrypt(public, value)
    assert value["claim_code"] not in json.dumps(envelope)
    assert decrypt(private, envelope) == value
    with pytest.raises(ValueError, match="authentication"):
        decrypt(other, envelope)


def test_tampering_and_oversize_are_rejected() -> None:
    private, public = keys()
    envelope = encrypt(public, {"state": "retired"})
    envelope["payload"] = "tampered"
    with pytest.raises(ValueError, match="authentication"):
        decrypt(private, envelope)
    with pytest.raises(ValueError, match="limit"):
        encrypt(public, {"large": "x" * MAX_PRIVATE_BYTES})
    with pytest.raises(ValueError, match="limit"):
        encrypt("x" * (MAX_PRIVATE_BYTES + 1), {})
