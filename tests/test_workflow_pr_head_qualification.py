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
            ".github/workflows/publish-docs-screenshots.yml",
            'website_owner="${WEBSITE_REPOSITORY%%/*}"',
            '--head "${website_owner}:${WEBSITE_BRANCH}"',
            2,
        ),
        (
            ".github/workflows/publish-docs-screenshots.yml",
            'screenshots_owner="${SCREENSHOTS_REPOSITORY%%/*}"',
            '--head "${screenshots_owner}:${SCREENSHOTS_BRANCH}"',
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
