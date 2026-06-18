from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-governance.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_release_governance_workflow_covers_release_control_files() -> None:
    workflow_text = _workflow_text()

    expected_paths = [
        ".github/release-allowed-signers",
        ".github/workflows/build-release.yml",
        ".github/workflows/release-governance.yml",
        "Makefile",
        "hushline/version.py",
        "scripts/release.py",
    ]

    for path in expected_paths:
        assert f'- "{path}"' in workflow_text


def test_release_governance_workflow_requires_admin_permission() -> None:
    workflow_text = _workflow_text()

    assert "repos/${REPOSITORY}/collaborators/${actor}/permission" in workflow_text
    assert "--jq '.permission'" in workflow_text
    assert 'if [ "$permission" != "admin" ]; then' in workflow_text
    assert "Only repository admins may author release-governed changes" in workflow_text


def test_release_governance_workflow_avoids_checkout_for_untrusted_prs() -> None:
    workflow_text = _workflow_text()

    assert "pull_request:" in workflow_text
    assert "actions/checkout" not in workflow_text
    assert "github.event.pull_request.body" not in workflow_text
    assert "github.event.pull_request.title" not in workflow_text


def test_release_governance_workflow_uses_pr_files_api() -> None:
    workflow_text = _workflow_text()

    assert 'pr_number="$(jq -r \'.pull_request.number\' "$GITHUB_EVENT_PATH")"' in workflow_text
    assert 'gh api --paginate "repos/${REPOSITORY}/pulls/${pr_number}/files"' in workflow_text
    assert "GITHUB_EVENT_PATH" in workflow_text
