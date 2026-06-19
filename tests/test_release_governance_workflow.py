from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-governance.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_release_governance_workflow_covers_release_control_files() -> None:
    workflow_text = _workflow_text()

    expected_path_fragments = [
        r"\.github/release-allowed-signers",
        r"\.github/workflows/",
        "build-release",
        "bump-personal-server-after-release",
        "bump-staging-after-release",
        "docs-screenshots",
        "publish-docs-screenshots",
        "release-governance",
        "Makefile",
        r"hushline/version\.py",
        r"scripts/release\.py",
    ]

    for path_fragment in expected_path_fragments:
        assert path_fragment in workflow_text


def test_release_governance_workflow_requires_admin_permission() -> None:
    workflow_text = _workflow_text()

    assert "repos/${REPOSITORY}/collaborators/${actor}/permission" in workflow_text
    assert "--jq '.permission'" in workflow_text
    assert 'if [ "$permission" != "admin" ]; then' in workflow_text
    assert "Only repository admins may author release-governed changes" in workflow_text


def test_release_governance_workflow_avoids_checkout_for_untrusted_prs() -> None:
    workflow_text = _workflow_text()

    assert "pull_request_target:" in workflow_text
    assert "pull_request:" not in workflow_text
    assert "actions/checkout" not in workflow_text
    assert "github.event.pull_request.body" not in workflow_text
    assert "github.event.pull_request.title" not in workflow_text


def test_release_governance_workflow_runs_for_every_pr() -> None:
    workflow_text = _workflow_text()
    trigger_section = workflow_text.split("permissions:", 1)[0]

    assert "paths:" not in trigger_section


def test_release_governance_workflow_authorizes_pr_author_not_triggering_actor() -> None:
    workflow_text = _workflow_text()

    assert 'actor="$(jq -r \'.pull_request.user.login\' "$GITHUB_EVENT_PATH")"' in workflow_text


def test_release_governance_workflow_requires_admin_triggering_actor_for_all_pr_events() -> None:
    workflow_text = _workflow_text()

    assert 'event_action="$(jq -r \'.action\' "$GITHUB_EVENT_PATH")"' in workflow_text
    assert 'triggering_actor="$(jq -r \'.sender.login\' "$GITHUB_EVENT_PATH")"' in workflow_text
    assert 'if [ "${EVENT_NAME}" = "pull_request_target" ]; then' in workflow_text
    assert '[ "${event_action}" = "synchronize" ]' not in workflow_text
    assert "repos/${REPOSITORY}/collaborators/${triggering_actor}/permission" in workflow_text
    assert 'if [ "$triggering_permission" != "admin" ]; then' in workflow_text
    assert "Only repository admins may update release-governed changes" in workflow_text


def test_release_governance_workflow_uses_pr_files_api_with_renames() -> None:
    workflow_text = _workflow_text()

    assert 'pr_number="$(jq -r \'.pull_request.number\' "$GITHUB_EVENT_PATH")"' in workflow_text
    assert 'gh api --paginate "repos/${REPOSITORY}/pulls/${pr_number}/files"' in workflow_text
    assert '(.previous_filename // "")' in workflow_text
    assert "awk -F '\\t'" in workflow_text
    assert "GITHUB_EVENT_PATH" in workflow_text


def test_release_governance_workflow_fails_closed_on_truncated_file_lists() -> None:
    workflow_text = _workflow_text()

    assert "expected_file_count=\"$(jq -r '.pull_request.changed_files'" in workflow_text
    assert 'if [ "$expected_file_count" -ge 3000 ]' in workflow_text
    assert 'if [ "$returned_file_count" -ge 300 ]; then' in workflow_text
