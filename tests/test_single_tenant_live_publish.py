"""Exercise interruption recovery and create-only remote refs with a fake Git transport."""

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from scripts.single_tenant_live_envelope import keys
from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_publish import Publisher
from scripts.single_tenant_live_request import Request
from tests.test_single_tenant_live_ledger import ORDER, OWNER, payload


class FakePublisher(Publisher):
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.app, self.infra = Path("app"), Path("infra")
        self.app_sha, self.infra_sha = "a" * 40, "b" * 40
        self.refs: dict[tuple[str, str], str] = {}
        self.commits: list[dict[str, Any]] = []
        self.fail_public = False
        self.fail_private = False
        self.calls: list[list[str]] = []
        self.retained: dict[str, tuple[str, dict[str, Any]]] = {}

    def commit(  # noqa: PLR0913 — publisher test double
        self, path: Path, base: str, filename: str, data: dict[str, Any], message: str
    ) -> str:
        self.commits.append(data)
        return ("1" if path == self.infra else "2") * 40

    def signed_request(  # noqa: PLR0913 — publisher retention test double
        self, path: Path, base: str, filename: str, data: dict[str, Any], message: str, anchor: str
    ) -> str:
        if anchor in self.retained:
            sha, prior = self.retained[anchor]
            if prior != data:
                raise ValueError("Retained request payload changed")
            return sha
        sha = self.commit(path, base, filename, data, message)
        self.retained[anchor] = (sha, data)
        return sha

    def git(self, path: Path, args: list[str], **kwargs: Any) -> str:
        self.calls.append(args)
        if args[0] == "ls-remote":
            sha = self.refs.get((str(path), args[-1]))
            return sha + "\t" + args[-1] + "\n" if sha else ""
        if args[0] == "push":
            sha, ref = args[-1].split(":", 1)
            if path == self.infra and self.fail_private:
                raise ValueError("Private publication interrupted")
            self.refs[str(path), ref] = sha
            if path == self.app and self.fail_public:
                raise ValueError("Public push succeeded before connection loss")
            return ""
        raise AssertionError("Unexpected Git operation")


@pytest.fixture()
def publisher(tmp_path: Path) -> FakePublisher:
    ledger = Ledger.create(tmp_path / "publish.sqlite3", Fernet.generate_key())
    ledger.reserve(ORDER, OWNER, payload())
    return FakePublisher(ledger)


def test_public_commit_contains_no_payment_owner_or_domain(publisher: FakePublisher) -> None:
    publisher.one(publisher.ledger.pending()[0])
    assert set(publisher.commits[1]) == {
        "order_id",
        "purpose",
        "revision",
        "config_ref",
        "source_ref",
        "infra_ref",
    }
    assert publisher.ledger.pending() == []
    pushes = [call for call in publisher.calls if call[0] == "push"]
    assert len(pushes) == 2
    assert all(
        call[1].startswith("--force-with-lease=refs/heads/single-tenant-") and call[1].endswith(":")
        for call in pushes
    )


@pytest.mark.parametrize("private", [True, False])
def test_interruption_recovers_only_exact_original_commits(
    publisher: FakePublisher, private: bool
) -> None:
    publisher.fail_private = private
    publisher.fail_public = not private
    with pytest.raises(ValueError, match="publication interrupted|connection loss"):
        publisher.one(publisher.ledger.pending()[0])
    request = publisher.ledger.pending()[0]
    assert request["private_sha"] == "1" * 40
    assert request["public_sha"] == "2" * 40
    publisher.fail_private = publisher.fail_public = False
    publisher.one(request)
    assert len(publisher.commits) == 2
    assert publisher.ledger.pending() == []


def test_existing_remote_ref_is_never_overwritten(publisher: FakePublisher) -> None:
    ref = f"refs/heads/single-tenant-config/{ORDER}/provision-1"
    publisher.refs["infra", ref] = "9" * 40
    with pytest.raises(ValueError, match="not owned"):
        publisher.one(publisher.ledger.pending()[0])
    assert publisher.refs["infra", ref] == "9" * 40
    assert not any(call[0] == "push" for call in publisher.calls)
    assert publisher.ledger.pending()[0]["public_sha"] == "2" * 40


def test_crash_before_ledger_checkpoint_reuses_retained_commits(
    publisher: FakePublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = publisher.ledger.checkpoint

    def crash(*args: Any, **kwargs: Any) -> None:
        raise ValueError("Checkpoint interrupted")

    monkeypatch.setattr(publisher.ledger, "checkpoint", crash)
    with pytest.raises(ValueError, match="interrupted"):
        publisher.one(publisher.ledger.pending()[0])
    assert publisher.ledger.pending()[0]["public_sha"] is None
    assert len(publisher.retained) == 2
    monkeypatch.setattr(publisher.ledger, "checkpoint", original)
    publisher.one(publisher.ledger.pending()[0])
    assert len(publisher.commits) == 2
    assert publisher.ledger.pending() == []


@pytest.mark.parametrize("purpose", ["upgrade", "retire"])
def test_release_metadata_is_private_to_upgrade_requests(tmp_path: Path, purpose: str) -> None:
    ledger = Ledger.create(tmp_path / "release.sqlite3", Fernet.generate_key())
    publisher = FakePublisher(ledger)
    value = payload()
    value["state"] = "ready"
    value["verification"] = "f" * 64
    _, value["claim_public_key"] = keys()
    target = {
        "tag": "v0.7.27",
        "source_sha": "3" * 40,
        "build_sha": "4" * 40,
        "previous_sha": "5" * 40,
    }
    if purpose == "retire":
        value["release"] = {**target, "state": "upgraded"}
        value["payment"]["cancelled_at"] = "2026-10-07T00:00:00+00:00"
    ledger.reserve(ORDER, OWNER, value)
    if purpose == "upgrade":
        ledger.queue_release(ORDER, OWNER, target)
    else:
        ledger.destroy(ORDER, OWNER)
    request = next(r for r in ledger.pending() if r["purpose"] == purpose)
    publisher.one(request)
    private, public = publisher.commits
    assert ("release" in private) is (purpose == "upgrade")
    assert "release" not in public
    parsed = Request(
        public,
        branch=f"single-tenant-request/{ORDER}/{purpose}-{request['revision']}",
        source=publisher.app_sha,
        infra=publisher.infra_sha,
    )
    assert parsed.private(private) == private
    pushes = [call[-1] for call in publisher.calls if call[0] == "push"]
    assert len(pushes) == (3 if purpose == "upgrade" else 2)
    if purpose == "upgrade":
        assert pushes[0] == "4" * 40 + ":refs/heads/single-tenant-build/" + ORDER + "/" + "3" * 40
