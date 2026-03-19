from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _workflow_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_cross_repo_auto_merge_workflows_use_owner_qualified_pr_heads() -> None:
    expectations = [
        (
            ".github/workflows/public-directory-weekly-report.yml",
            'stats_owner="${STATS_REPOSITORY%%/*}"',
            '--head "${stats_owner}:${STATS_BRANCH}"',
            2,
        ),
        (
            ".github/workflows/bump-staging-after-release.yml",
            'infra_owner="${INFRA_REPOSITORY%%/*}"',
            '--head "${infra_owner}:${INFRA_BRANCH}"',
            2,
        ),
        (
            ".github/workflows/bump-personal-server-after-release.yml",
            'personal_server_owner="${PERSONAL_SERVER_REPOSITORY%%/*}"',
            '--head "${personal_server_owner}:${PERSONAL_SERVER_BRANCH}"',
            2,
        ),
    ]

    for workflow_path, owner_assignment, head_filter, expected_count in expectations:
        workflow_text = _workflow_text(workflow_path)

        assert owner_assignment in workflow_text
        assert workflow_text.count(head_filter) == expected_count


def test_screenshots_archive_workflow_publishes_directly_without_pr_flow() -> None:
    workflow_text = _workflow_text(".github/workflows/publish-docs-screenshots.yml")
    artifact_section = workflow_text.split("      - name: Download screenshot artifact", 1)[
        1
    ].split("      - name: Publish screenshots to hushline-screenshots", 1)[0]
    archive_section = workflow_text.split(
        "      - name: Publish screenshots to hushline-screenshots", 1
    )[1]

    assert "rm -f /tmp/docs-screenshots-artifact/artifact.zip" in artifact_section
    assert "SCREENSHOTS_DEFAULT_BRANCH: main" in archive_section
    assert "--depth 1" in archive_section
    assert "--filter=blob:none" in archive_section
    assert "--single-branch" in archive_section
    assert "git sparse-checkout init --no-cone" in archive_section
    assert (
        "git sparse-checkout set README.md badge-docs-screenshots.json releases/latest "
        '"releases/${RELEASE_KEY}"' in archive_section
    )
    assert (
        'git checkout -B "${SCREENSHOTS_DEFAULT_BRANCH}" "origin/${SCREENSHOTS_DEFAULT_BRANCH}"'
        in archive_section
    )
    assert 'git push origin "HEAD:${SCREENSHOTS_DEFAULT_BRANCH}"' in archive_section
    assert (
        "Published screenshot archive directly to "
        "${SCREENSHOTS_REPOSITORY}@${SCREENSHOTS_DEFAULT_BRANCH}." in archive_section
    )
    assert 'screenshots_owner="${SCREENSHOTS_REPOSITORY%%/*}"' not in archive_section
    assert "gh pr create \\" not in archive_section
    assert 'gh pr merge "$pr_url" \\' not in archive_section


def test_dev_deploy_workflow_generates_session_fernet_key_for_terraform_runs() -> None:
    workflow_text = _workflow_text(".github/workflows/dev_deploy.yml")

    assert workflow_text.count("- name: Generate session fernet key") == 2
    assert workflow_text.count("python3 - <<'PY' >> \"$GITHUB_OUTPUT\"") == 2
    assert "base64.urlsafe_b64encode(os.urandom(32)).decode()" in workflow_text
    assert (
        workflow_text.count(
            'SESSION_FERNET_KEY = "${{ steps.session-fernet-key.outputs.session_fernet_key }}"'
        )
        == 4
    )


def test_tests_workflow_lint_job_uses_host_python_313() -> None:
    workflow_text = _workflow_text(".github/workflows/tests.yml")
    lint_section = workflow_text.split("  lint:\n", 1)[1].split("  test:\n", 1)[0]

    assert "actions/setup-python" in lint_section
    assert 'python-version: "3.13"' in lint_section
    assert 'python-version: "3.12"' not in lint_section


def test_dependency_audit_workflow_only_runs_python_audit_when_poetry_lock_changes() -> None:
    workflow_text = _workflow_text(".github/workflows/dependency-security-audit.yml")
    detect_section = workflow_text.split("  detect-python-lockfile-change:\n", 1)[1].split(
        "  python-audit:\n", 1
    )[0]
    python_audit_section = workflow_text.split("  python-audit:\n", 1)[1].split(
        "  node-runtime-audit:\n", 1
    )[0]

    assert "git diff --name-only" in detect_section
    assert "grep -Fxq 'poetry.lock'" in detect_section
    assert "pyproject.toml" not in detect_section
    assert "needs: detect-python-lockfile-change" in python_audit_section
    assert (
        "if: needs.detect-python-lockfile-change.outputs.poetry_lock_changed == 'true'"
        in python_audit_section
    )
