"""Lost callbacks recover authenticated results without repeating cloud operations."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from scripts.single_tenant_live_collect import Collector
from scripts.single_tenant_live_envelope import encrypt, keys
from scripts.single_tenant_live_ledger import Ledger
from tests.test_single_tenant_live_ledger import ORDER, OWNER, payload
from tests.test_single_tenant_live_publish import FakePublisher


@pytest.fixture()
def collector(tmp_path: Path) -> tuple[Collector, dict[str, Any]]:
    ledger = Ledger.create(tmp_path / "results.sqlite3", Fernet.generate_key())
    private, public = keys()
    data = payload()
    data.update(claim_private_key=private, claim_public_key=public)
    ledger.reserve(ORDER, OWNER, data)
    ledger.checkpoint(ORDER, "provision", 1, private_sha="1" * 40, public_sha="2" * 40)
    publisher = FakePublisher(ledger)
    publisher.git = lambda path, args, **kwargs: "3" * 40  # type: ignore[method-assign]
    documents: dict[str, Any] = {}
    run = {
        "id": 101,
        "status": "completed",
        "event": "workflow_run",
        "run_attempt": 1,
        "head_sha": "4" * 40,
    }
    prefix = "repos/scidsg/hushline/"
    documents[
        prefix
        + "actions/workflows/single_tenant_lifecycle.yml/runs?event=workflow_run&per_page=30&page=1"
    ] = {"workflow_runs": [run]}
    documents[
        prefix
        + "actions/workflows/single_tenant_lifecycle.yml/runs?event=workflow_run&per_page=30&page=2"
    ] = {"workflow_runs": []}
    documents[prefix + "actions/runs/101"] = run
    documents[prefix + "contents/.github/workflows/single_tenant_lifecycle.yml?ref=" + "4" * 40] = {
        "sha": "3" * 40
    }
    documents[prefix + "actions/runs/101/artifacts"] = {
        "artifacts": [{"id": 201, "name": "single-tenant-result-101", "expired": False}]
    }
    result = {"state": "provisioning", "checks": {"infrastructure": True}}
    body = {
        "order_id": ORDER,
        "owner": OWNER,
        "purpose": "provision",
        "revision": 1,
        "public_sha": "2" * 40,
        "result": encrypt(public, result),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "single-tenant-result.json", json.dumps({"ciphertext": encrypt(public, body)})
        )
    documents[prefix + "actions/artifacts/201/zip"] = archive.getvalue()

    def api(path: str) -> bytes:
        value = documents[path]
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    return Collector(ledger=ledger, publisher=publisher, api=api), documents


def test_missed_callback_recovers_exact_checkpoint_once(collector: tuple[Collector, dict]) -> None:
    worker, _ = collector
    assert worker.reconcile() == 1
    assert worker.ledger.get(ORDER, OWNER)["checks"]["infrastructure"] is True
    assert worker.ledger.get(ORDER, OWNER)["state"] == "provisioning"
    assert worker.ledger.unfinished_runs() == []
    assert worker.reconcile() == 0
    assert len(worker.ledger.pending()) == 1  # Callback recovery never republishes a request.


def test_artifact_checkpoint_crash_finishes_without_replaying(
    collector: tuple[Collector, dict],
) -> None:
    worker, _ = collector
    worker.discover()
    worker.ledger.artifact_record("201")
    assert worker.reconcile() == 0
    assert worker.ledger.unfinished_runs() == []


@pytest.mark.parametrize(("field", "value"), [("run_attempt", 2), ("event", "push")])
def test_untrusted_attempt_cannot_supply_result(
    collector: tuple[Collector, dict], field: str, value: Any
) -> None:
    worker, documents = collector
    documents["repos/scidsg/hushline/actions/runs/101"][field] = value
    assert worker.reconcile() == 0
    assert worker.ledger.get(ORDER, OWNER)["state"] == "queued"
    assert not worker.ledger.artifact_seen("201")


def test_older_in_progress_run_is_not_lost_at_cursor(collector: tuple[Collector, dict]) -> None:
    worker, documents = collector
    documents["repos/scidsg/hushline/actions/runs/101"]["status"] = "in_progress"
    assert worker.reconcile() == 0
    assert worker.ledger.collection_cursor() == 101
    assert worker.ledger.unfinished_runs() == ["101"]
    documents["repos/scidsg/hushline/actions/runs/101"]["status"] = "completed"
    assert worker.reconcile() == 1


def test_completed_run_waits_for_artifact_visibility(collector: tuple[Collector, dict]) -> None:
    worker, documents = collector
    artifacts = documents["repos/scidsg/hushline/actions/runs/101/artifacts"]
    original = artifacts["artifacts"]
    artifacts["artifacts"] = []
    assert worker.reconcile() == 0
    assert worker.ledger.unfinished_runs() == ["101"]
    artifacts["artifacts"] = original
    assert worker.reconcile() == 1


def test_trusted_failed_job_before_driver_reports_original_order(
    collector: tuple[Collector, dict],
) -> None:
    worker, documents = collector
    worker.ledger.published(ORDER, "provision", 1, private_sha="1" * 40, public_sha="2" * 40)
    run = documents["repos/scidsg/hushline/actions/runs/101"]
    run.update(
        conclusion="failure",
        updated_at="2026-01-01T00:00:00Z",
        display_title=f"Single Tenant single-tenant-request/{ORDER}/provision-1",
    )
    documents["repos/scidsg/hushline/actions/runs/101/artifacts"]["artifacts"] = []
    assert worker.reconcile() == 0
    assert worker.ledger.get(ORDER, OWNER)["state"] == "failed"
    assert worker.ledger.get(ORDER, OWNER)["failure_stage"] == "workflow-preflight"
    assert worker.ledger.unfinished_runs() == []


def test_failed_foreign_job_cannot_change_saved_order(collector: tuple[Collector, dict]) -> None:
    worker, documents = collector
    run = documents["repos/scidsg/hushline/actions/runs/101"]
    run.update(
        conclusion="failure",
        updated_at="2026-01-01T00:00:00Z",
        display_title=f"Single Tenant single-tenant-request/{'e' * 32}/provision-1",
    )
    documents["repos/scidsg/hushline/actions/runs/101/artifacts"]["artifacts"] = []
    assert worker.reconcile() == 0
    assert worker.ledger.get(ORDER, OWNER)["state"] == "queued"


@pytest.mark.parametrize("failure", [None, "review", "branch", "secret"])
def test_release_gate_requires_review_free_default_branch_customer_environment(
    collector: tuple[Collector, dict], failure: str | None
) -> None:
    worker, documents = collector
    prefix = "repos/scidsg/hushline/environments/single-tenant-automation"
    environment: dict[str, Any] = {
        "name": "single-tenant-automation",
        "protection_rules": [],
        "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
    }
    branches: dict[str, Any] = {
        "total_count": 1,
        "branch_policies": [{"id": 1, "name": "main", "type": "branch"}],
    }
    secret_names = [
        "SINGLE_TENANT_CONFIG_READ_TOKEN",
        "SINGLE_TENANT_DO_TOKEN",
        "SINGLE_TENANT_TF_TOKEN",
        "SINGLE_TENANT_PORTAL_KEY",
        "SINGLE_TENANT_WORKFLOW_KEY",
        "SINGLE_TENANT_SMTP_JSON",
    ]
    if failure == "review":
        environment["protection_rules"] = [{"type": "required_reviewers"}]
    if failure == "branch":
        branches["branch_policies"][0]["name"] = "*"
    if failure == "secret":
        secret_names.pop()
    documents[prefix] = environment
    documents[prefix + "/deployment-branch-policies"] = branches
    documents[prefix + "/secrets"] = {"secrets": [{"name": name} for name in secret_names]}
    for name in (
        "SINGLE_TENANT_TF_ORGANIZATION",
        "SINGLE_TENANT_TF_PROJECT",
        "SINGLE_TENANT_DO_TEAM_ID",
        "SINGLE_TENANT_AUTHORITY_ORIGIN",
        "SINGLE_TENANT_CONTROL_ORIGIN",
    ):
        documents["repos/scidsg/hushline/actions/variables/" + name] = {"value": "configured"}
    if failure:
        with pytest.raises(ValueError, match="environment|branch|credentials"):
            worker.environment()
    else:
        worker.environment()
