import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_workflow_pr_head_qualification.py"
spec = importlib.util.spec_from_file_location("check_workflow_pr_head_qualification", SCRIPT_PATH)
assert spec is not None
workflow_guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(workflow_guard)


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


def test_personal_server_bump_workflow_rebuilds_release_branch_from_main() -> None:
    workflow_text = _workflow_text(".github/workflows/bump-personal-server-after-release.yml")
    branch_section = workflow_text.split(
        "      - name: Create clean release branch in hushline-personal-server", 1
    )[1].split("      - name: Update personal server package and image references", 1)[0]
    update_section = workflow_text.split(
        "      - name: Update personal server package and image references", 1
    )[1].split("      - name: Commit and push personal server branch", 1)[0]
    commit_section = workflow_text.split("      - name: Commit and push personal server branch", 1)[
        1
    ].split("      - name: Verify only the generated personal server version diff changed", 1)[0]
    merge_section = workflow_text.split(
        "      - name: Merge personal server PR if immediately allowed", 1
    )[1]

    assert 'git ls-remote --exit-code --heads origin "$PERSONAL_SERVER_BRANCH"' in branch_section
    assert (
        'git fetch origin "$PERSONAL_SERVER_BRANCH":'
        '"refs/remotes/origin/$PERSONAL_SERVER_BRANCH"' in branch_section
    )
    assert (
        'git checkout -B "$PERSONAL_SERVER_BRANCH" "origin/$PERSONAL_SERVER_BASE_REF"'
        in branch_section
    )
    assert (
        'git checkout -B "$PERSONAL_SERVER_BRANCH" "origin/$PERSONAL_SERVER_BRANCH"'
        not in branch_section
    )
    assert "origin/$PERSONAL_SERVER_BASE_REF...HEAD" not in update_section
    assert "branch already contains" not in update_section
    assert 'echo "head_sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"' in commit_section
    assert (
        '--match-head-commit "${{ steps.commit_personal_server.outputs.head_sha }}"'
        in merge_section
    )


def test_public_directory_weekly_report_refreshes_stats_branch_lease_before_push() -> None:
    workflow_text = _workflow_text(".github/workflows/public-directory-weekly-report.yml")
    build_section = workflow_text.split("      - name: Build weekly directory report", 1)[1].split(
        "      - name: Publish workflow summary", 1
    )[0]
    publish_section = workflow_text.split("      - name: Commit and open stats PR", 1)[1]

    assert 'echo "REPORT_TIMESTAMP=${REPORT_TIMESTAMP}" >> "$GITHUB_ENV"' in build_section
    assert 'REPORT_TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"' not in publish_section
    assert (
        'git fetch origin "+refs/heads/${STATS_DEFAULT_BRANCH}:'
        'refs/remotes/origin/${STATS_DEFAULT_BRANCH}"' in publish_section
    )
    assert "stats_branch_exists=false" in publish_section
    assert 'git ls-remote --exit-code --heads origin "${STATS_BRANCH}"' in publish_section
    assert (
        'git fetch origin "+refs/heads/${STATS_BRANCH}:'
        'refs/remotes/origin/${STATS_BRANCH}"' in publish_section
    )
    assert "push_stats_branch() {" in publish_section
    assert '--force-with-lease=refs/heads/"${STATS_BRANCH}"' in publish_section
    assert 'git push origin "HEAD:${STATS_BRANCH}"' in publish_section
    assert "Stats branch push failed; refreshing remote lease and retrying once." in publish_section


def test_screenshots_archive_workflow_publishes_directly_without_pr_flow() -> None:
    workflow_text = _workflow_text(".github/workflows/publish-docs-screenshots.yml")
    source_section = workflow_text.split("      - name: Verify trusted source run", 1)[1].split(
        "      - name: Download screenshot artifact", 1
    )[0]
    artifact_section = workflow_text.split("      - name: Download screenshot artifact", 1)[
        1
    ].split("      - name: Publish screenshots to hushline-screenshots", 1)[0]
    archive_section = workflow_text.split(
        "      - name: Publish screenshots to hushline-screenshots", 1
    )[1].split("      - name: Publish current screenshots to hushline-website", 1)[0]

    assert 'run.get("event") != "release"' in source_section
    assert 'run.get("path") != ".github/workflows/docs-screenshots.yml"' in source_section
    assert 'head_repository.get("full_name") != os.environ["GITHUB_REPOSITORY"]' in source_section
    assert (
        'JOBS_JSON="$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/jobs")"'
        in source_section
    )
    assert "capture_succeeded = any(" in source_section
    assert 'job.get("name") == "capture"' in source_section
    assert 'job.get("conclusion") == "success"' in source_section
    assert 'run.get("conclusion") != "success" and not capture_succeeded' in source_section
    assert "rm -f /tmp/docs-screenshots-artifact/artifact.zip" in artifact_section
    assert "path.is_symlink()" in artifact_section
    assert 'Path("screenshots/release/README.md")' in artifact_section
    assert 'Path("screenshots", "releases", release_key, "README.md")' in artifact_section
    assert 'is_current_image = relative.parts[:2] == ("screenshots", "current")' in artifact_section
    assert 'is_release_image = relative.parts[:2] == ("screenshots", "release")' in artifact_section
    assert "is_legacy_release_image = relative.parts[:3]" in artifact_section
    assert "path.suffix.lower() in image_extensions" in artifact_section
    assert "SCREENSHOTS_DEFAULT_BRANCH: main" in archive_section
    assert 'SCREENSHOT_ROOT="${ARTIFACT_DIR}/screenshots/release"' in archive_section
    assert (
        'LEGACY_RELEASE_ROOT="${ARTIFACT_DIR}/screenshots/releases/${RELEASE_KEY}"'
        in archive_section
    )
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
    assert 'GIT_ASKPASS="${RUNNER_TEMP}/hushline-screenshots-git-askpass.sh"' in archive_section
    assert '"https://github.com/${SCREENSHOTS_REPOSITORY}.git"' in archive_section
    assert "x-access-token:${SCREENSHOTS_PUSH_TOKEN}@github.com" not in archive_section
    assert 'git push origin "HEAD:${SCREENSHOTS_DEFAULT_BRANCH}"' in archive_section
    assert (
        "Published screenshot archive directly to "
        "${SCREENSHOTS_REPOSITORY}@${SCREENSHOTS_DEFAULT_BRANCH}." in archive_section
    )
    assert 'screenshots_owner="${SCREENSHOTS_REPOSITORY%%/*}"' not in archive_section
    assert "gh pr create \\" not in archive_section
    assert 'gh pr merge "$pr_url" \\' not in archive_section


def test_screenshots_workflow_publishes_current_folder_to_website_directly() -> None:
    capture_workflow_text = _workflow_text(".github/workflows/docs-screenshots.yml")
    publish_workflow_text = _workflow_text(".github/workflows/publish-docs-screenshots.yml")
    publish_job_section = capture_workflow_text.split("  publish-release:", 1)[1]
    artifact_section = capture_workflow_text.split("      - name: Prepare publish artifact", 1)[
        1
    ].split("      - name: Upload screenshot artifacts", 1)[0]
    checkout_section = capture_workflow_text.split(
        "      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", 1
    )[1].split("      - name: Check screenshot manifest", 1)[0]
    trusted_checkout_section = capture_workflow_text.split(
        "      - name: Check out trusted workflow scripts", 1
    )[1].split("      - name: Set up Docker Buildx", 1)[0]
    website_section = publish_workflow_text.split(
        "      - name: Publish current screenshots to hushline-website", 1
    )[1]

    assert "if: ${{ github.event_name == 'release' }}" in publish_job_section
    assert "if: ${{ github.event_name != 'workflow_call' }}" not in capture_workflow_text
    assert "fetch-depth: 1" in checkout_section
    assert "fetch-depth: 0" not in checkout_section
    assert "repository: ${{ job.workflow_repository }}" in trusted_checkout_section
    assert "ref: ${{ job.workflow_sha }}" in trusted_checkout_section
    assert "ref: ${{ github.workflow_sha }}" not in trusted_checkout_section
    assert "Resolve screenshot capture manifest" in capture_workflow_text
    assert "DOCS_REPOSITORY: scidsg/hushline-docs" in capture_workflow_text
    assert 'DOCS_DIR="${RUNNER_TEMP}/hushline-docs"' in capture_workflow_text
    assert '--branch "$branch"' in capture_workflow_text
    assert (
        'clone_with_optional_token "$DOCS_REPOSITORY" "$DOCS_DEFAULT_BRANCH"'
        in capture_workflow_text
    )
    assert '--docs-dir "$DOCS_DIR"' in capture_workflow_text
    assert '--manifest-out "$CAPTURE_MANIFEST"' in capture_workflow_text
    assert '--output "$CAPTURE_FILES"' in capture_workflow_text
    assert 'cp -R "$RELEASE_ROOT" "${ARTIFACT_ROOT}/screenshots/release"' in artifact_section
    assert (
        'cp "${{ steps.capture_manifest.outputs.capture_files }}" '
        '"${ARTIFACT_ROOT}/capture_files.json"' in artifact_section
    )
    assert '"${ARTIFACT_ROOT}/screenshots/current"' not in artifact_section
    assert '"${ARTIFACT_ROOT}/screenshots/releases/latest"' not in artifact_section
    assert "WEBSITE_REPOSITORY: scidsg/hushline-website" in website_section
    assert "WEBSITE_DEFAULT_BRANCH: main" in website_section
    assert "WEBSITE_SCREENSHOT_ROOT: src/assets/img/screenshots" in website_section
    assert 'CURRENT_ROOT="${ARTIFACT_DIR}/screenshots/release"' in website_section
    assert 'LEGACY_CURRENT_ROOT="${ARTIFACT_DIR}/screenshots/current"' in website_section
    assert '--branch "${WEBSITE_DEFAULT_BRANCH}"' in website_section
    assert 'GIT_ASKPASS="${RUNNER_TEMP}/hushline-website-git-askpass.sh"' in website_section
    assert '"https://github.com/${WEBSITE_REPOSITORY}.git"' in website_section
    assert "x-access-token:${WEBSITE_PUSH_TOKEN}@github.com" not in website_section
    assert 'git sparse-checkout set "${WEBSITE_SCREENSHOT_ROOT}/current"' not in website_section
    assert '--refs-input "${ARTIFACT_DIR}/capture_files.json"' in website_section
    assert '--current-root "$CURRENT_ROOT"' in website_section
    assert '--filtered-root "$FILTERED_CURRENT_ROOT"' in website_section
    assert 'mkdir -p "${WEBSITE_SCREENSHOT_ROOT}/current"' in website_section
    assert (
        'rsync -a --delete "${FILTERED_CURRENT_ROOT}/" '
        '"${WEBSITE_SCREENSHOT_ROOT}/current/"' in website_section
    )
    assert 'git add "${WEBSITE_SCREENSHOT_ROOT}/current"' in website_section
    assert 'git push origin "HEAD:${WEBSITE_DEFAULT_BRANCH}"' in website_section
    assert "gh pr create \\" not in website_section
    assert 'gh pr merge "$pr_url" \\' not in website_section
    assert "${WEBSITE_SCREENSHOT_ROOT}/releases" not in website_section


def test_docs_screenshot_release_tag_is_validated_before_shell_use() -> None:
    workflow_text = _workflow_text(".github/workflows/docs-screenshots.yml")
    validate_section = workflow_text.split("      - name: Validate release tag", 1)[1].split(
        "      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", 1
    )[0]
    resolve_section = workflow_text.split("      - name: Resolve release key", 1)[1].split(
        "      - name: Resolve screenshot capture manifest", 1
    )[0]

    assert "EVENT_RELEASE_TAG: ${{ github.event.release.tag_name }}" in validate_section
    assert 'os.environ["EVENT_RELEASE_TAG"].strip()' in validate_section
    assert 're.fullmatch(r"v[0-9]+\\.[0-9]+\\.[0-9]+", release_tag)' in validate_section
    assert 'RELEASE_KEY="${{ inputs.release_key }}"' not in resolve_section
    assert 'RELEASE_KEY="${{ github.event.release.tag_name }}"' not in resolve_section
    assert 'RELEASE_KEY="${INPUT_RELEASE_KEY:-}"' in resolve_section
    assert 'RELEASE_KEY="${EVENT_RELEASE_TAG:-}"' in resolve_section
    assert "INPUT_RELEASE_KEY: ${{ inputs.release_key }}" in resolve_section
    assert "EVENT_RELEASE_TAG: ${{ github.event.release.tag_name }}" in resolve_section


def test_docs_screenshot_capture_manifest_does_not_persist_read_tokens() -> None:
    workflow_text = _workflow_text(".github/workflows/docs-screenshots.yml")
    manifest_section = workflow_text.split("      - name: Resolve screenshot capture manifest", 1)[
        1
    ].split("      - name: Capture screenshots", 1)[0]

    assert "DOCS_READ_TOKEN:" in manifest_section
    assert "WEBSITE_READ_TOKEN:" in manifest_section
    assert "GIT_ASKPASS_HELPER=" in manifest_section
    assert 'GIT_ASKPASS_TOKEN="$token"' in manifest_section
    assert 'git -C "$destination" remote set-url origin "$clone_url"' in manifest_section
    assert "https://x-access-token:${DOCS_READ_TOKEN}" not in manifest_section
    assert "https://x-access-token:${WEBSITE_READ_TOKEN}" not in manifest_section
    assert "DOCS_CLONE_URL=" not in manifest_section


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


def test_securedrop_refresh_summary_uses_checked_random_github_output_delimiter() -> None:
    workflow_text = _workflow_text(".github/workflows/securedrop-directory-refresh.yml")
    summary_section = workflow_text.split("      - name: Read refresh summary", 1)[1].split(
        "      - name: Create or update refresh PR",
        1,
    )[0]

    assert 'delimiter="SECUREDROP_SUMMARY_$(uuidgen)"' in summary_section
    assert 'grep -Fxq "$delimiter" "$payload_path"' in summary_section
    assert 'delimiter="SECUREDROP_SUMMARY_$(date +%s)"' not in summary_section


def test_epic_child_close_workflow_uses_trusted_head_branch_not_pr_body() -> None:
    workflow_text = _workflow_text(".github/workflows/close-epic-child-issue-on-merge.yml")

    assert "pull_request_target:" in workflow_text
    assert "issues: write" in workflow_text
    assert "pullRequest.head.repo?.full_name" in workflow_text
    assert "headRepo !== expectedRepo" in workflow_text
    assert "baseRef.match(/^codex\\/epic-(\\d+)$/)" in workflow_text
    assert "headRef.match(/^codex\\/daily-issue-(\\d+)$/)" in workflow_text
    assert "const issueNumber = Number(headMatch[1]);" in workflow_text
    assert "context.payload.pull_request.body" not in workflow_text
    assert "Linked issue:" not in workflow_text


def test_workflow_pr_head_guard_rejects_unqualified_long_head_with_equals() -> None:
    command = "gh pr list --repo owner/repo --head=feature-branch"

    assert workflow_guard.is_unqualified_head(command) is True


def test_workflow_pr_head_guard_allows_qualified_long_head_with_equals() -> None:
    command = "gh pr list --repo owner/repo --head=owner:feature-branch"

    assert workflow_guard.is_unqualified_head(command) is False


def test_workflow_pr_head_guard_rejects_unqualified_short_head() -> None:
    command = "gh pr create --repo owner/repo -H feature-branch"

    assert workflow_guard.is_unqualified_head(command) is True


def test_workflow_pr_head_guard_allows_qualified_short_head_with_equals() -> None:
    command = "gh pr create --repo owner/repo -H=owner:feature-branch"

    assert workflow_guard.is_unqualified_head(command) is False


def test_workflow_pr_head_guard_rejects_missing_head_value_with_repo() -> None:
    command = "gh pr create --repo owner/repo --head"

    assert workflow_guard.is_unqualified_head(command) is True
