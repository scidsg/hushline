from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = ROOT / "scripts" / "agent_dependabot_pr_runner.sh"


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-lc", script],  # noqa: S603 - controlled test harness invocation
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_runner_defaults_repo_dir_to_checkout_root() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
printf '%s\\n' "$REPO_DIR"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == ROOT


def test_select_dependabot_pr_picks_oldest_maintainer_editable_pr() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
DEPENDABOT_PR_JSON_FILE="$(mktemp)"
gh() {{
  if [[ "${{1-}} ${{2-}}" == "pr list" ]]; then
    cat <<'EOF'
[
  {{
    "number": 202,
    "createdAt": "2026-03-20T08:00:00Z",
    "maintainerCanModify": true,
    "title": "Bump urllib3"
  }},
  {{
    "number": 201,
    "createdAt": "2026-03-19T08:00:00Z",
    "maintainerCanModify": true,
    "title": "Bump cryptography"
  }},
  {{
    "number": 200,
    "createdAt": "2026-03-18T08:00:00Z",
    "maintainerCanModify": false,
    "title": "Bump flask"
  }}
]
EOF
    return 0
  fi

  if [[ "${{1-}} ${{2-}} ${{3-}}" == "pr view 201" ]]; then
    cat <<'EOF'
{{
  "number": 201,
  "title": "Bump cryptography from 43.0.1 to 43.0.3",
  "body": "Dependabot body",
  "url": "https://github.com/scidsg/hushline/pull/201",
  "headRefName": "dependabot/pip/cryptography-43.0.3",
  "baseRefName": "main",
  "author": {{"login": "app/dependabot"}},
  "maintainerCanModify": true
}}
EOF
    return 0
  fi

  return 1
}}
select_dependabot_pr
printf '%s\\n%s\\n%s\\n' "$PR_NUMBER" "$PR_TITLE" "$PR_HEAD_REF_NAME"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "201\n" "Bump cryptography from 43.0.1 to 43.0.3\n" "dependabot/pip/cryptography-43.0.3\n"
    )


def test_build_dependabot_prompt_includes_pr_context() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PROMPT_FILE="$(mktemp)"
DEPENDABOT_PR_JSON_FILE="$(mktemp)"
PR_NUMBER=201
PR_TITLE="Bump cryptography from 43.0.1 to 43.0.3"
PR_URL="https://github.com/scidsg/hushline/pull/201"
PR_BODY="Dependabot body"
PR_HEAD_REF_NAME="dependabot/pip/cryptography-43.0.3"
PR_BASE_REF_NAME="main"
cat > "$DEPENDABOT_PR_JSON_FILE" <<'EOF'
{{
  "files": [
    {{"path": "pyproject.toml", "additions": 1, "deletions": 1}},
    {{"path": "poetry.lock", "additions": 6, "deletions": 6}}
  ]
}}
EOF
current_pr_diff_stat() {{
  printf ' pyproject.toml | 2 +-\\n poetry.lock | 12 ++++++------\\n'
}}
make() {{
  printf 'unexpected make invocation\\n' >&2
  return 99
}}
build_dependabot_prompt
cat "$PROMPT_FILE"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "PR number: #201" in result.stdout
    assert "Bump cryptography from 43.0.1 to 43.0.3" in result.stdout
    assert "Dependabot body" not in result.stdout
    assert "Do not include PR body text in this prompt." in result.stdout
    assert "pyproject.toml (+1 / -1)" in result.stdout
    assert "poetry.lock (+6 / -6)" in result.stdout
    assert "If no follow-up changes are needed, leave the branch unchanged." in result.stdout


def test_main_exits_before_runtime_bootstrap_when_no_dependabot_pr_exists(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
parse_args() {{ :; }}
initialize_run_state() {{ :; }}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs() {{ printf '0\\n'; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
select_dependabot_pr() {{
  printf 'select-dependabot-pr\\n' >> {shlex.quote(str(call_log))}
  return 1
}}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: no eligible open Dependabot PRs were found." in result.stdout
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "select-dependabot-pr" in calls
    assert "runtime-bootstrap" not in calls


def test_main_exits_early_when_human_pr_is_open(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
parse_args() {{ :; }}
initialize_run_state() {{ :; }}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
count_open_human_prs() {{ printf '2\\n'; }}
count_open_bot_prs() {{ printf '0\\n'; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
select_dependabot_pr() {{
  printf 'select-dependabot-pr\\n' >> {shlex.quote(str(call_log))}
  return 0
}}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: found 2 open human-authored PR(s)." in result.stdout
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "select-dependabot-pr" not in calls
    assert "runtime-bootstrap" not in calls


def test_count_open_human_prs_excludes_dependabot_and_bot_logins() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
gh() {{
  if [[ "${{1-}} ${{2-}}" == "pr list" ]]; then
    cat <<'EOF'
[
  {{"author": {{"login": "app/dependabot"}}}},
  {{"author": {{"login": "dependabot[bot]"}}}},
  {{"author": {{"login": "hushline-dev"}}}},
  {{"author": {{"login": "Alice"}}}}
]
EOF
    return 0
  fi

  return 1
}}
count_open_human_prs
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"


def test_main_exits_early_when_unrelated_bot_pr_is_open(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
parse_args() {{ :; }}
initialize_run_state() {{ :; }}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs() {{ printf '1\\n'; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
select_dependabot_pr() {{
  printf 'select-dependabot-pr\\n' >> {shlex.quote(str(call_log))}
  return 0
}}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: found 1 open PR(s) by hushline-dev." in result.stdout
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "select-dependabot-pr" not in calls
    assert "runtime-bootstrap" not in calls


def test_main_pushes_follow_up_commit_and_comments_on_pr(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
parse_args() {{ :; }}
initialize_run_state() {{
  CHECK_LOG_FILE={shlex.quote(str(tmp_path / "check.log"))}
  PROMPT_FILE={shlex.quote(str(tmp_path / "prompt.txt"))}
  COMMENT_BODY_FILE={shlex.quote(str(tmp_path / "comment.txt"))}
  CODEX_OUTPUT_FILE={shlex.quote(str(tmp_path / "codex-output.txt"))}
  CODEX_TRANSCRIPT_FILE={shlex.quote(str(tmp_path / "codex-transcript.txt"))}
  RUN_LOG_TMP_FILE={shlex.quote(str(tmp_path / "run.log"))}
  DEPENDABOT_PR_JSON_FILE={shlex.quote(str(tmp_path / "pr.json"))}
  RUN_LOG_TIMESTAMP=20260320T000000Z
}}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs() {{ printf '0\\n'; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
select_dependabot_pr() {{
  PR_NUMBER=201
  PR_TITLE="Bump cryptography"
  PR_URL="https://github.com/scidsg/hushline/pull/201"
  PR_BODY="Dependabot body"
  PR_HEAD_REF_NAME="dependabot/pip/cryptography-43.0.3"
  PR_BASE_REF_NAME="main"
  cat > "$DEPENDABOT_PR_JSON_FILE" <<'EOF'
{{"files":[{{"path":"pyproject.toml","additions":1,"deletions":1}}]}}
EOF
}}
configure_bot_git_identity() {{ :; }}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{ :; }}
remote_branch_exists() {{ return 0; }}
build_dependabot_prompt() {{ :; }}
run_codex_from_prompt() {{
  cat > "$CODEX_OUTPUT_FILE" <<'EOF'
Applied compatibility updates for the dependency bump.
EOF
}}
run_fix_attempt_loop() {{ return 0; }}
persist_run_log() {{
  RUN_LOG_GIT_PATH="docs/agent-logs/run-20260320T000000Z-dependabot-pr-$1.txt"
  printf 'persist:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
has_changes() {{ return 0; }}
docker() {{ :; }}
push_branch_for_pr() {{
  printf 'push:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
git() {{
  local fetch_branch_ref
  fetch_branch_ref=$(
    printf '%s' \
      "fetch origin dependabot/pip/cryptography-43.0.3:refs/remotes/origin/" \
      "dependabot/pip/cryptography-43.0.3"
  )
  case "${{1-}} ${{2-}} ${{3-}}" in
    "fetch origin") return 0 ;;
    "checkout main") return 0 ;;
    "reset --hard origin/main") return 0 ;;
    "clean -fd") return 0 ;;
    "$fetch_branch_ref") return 0 ;;
    "checkout -B dependabot/pip/cryptography-43.0.3") return 0 ;;
    "add -A ") printf 'git-add\\n' >> {shlex.quote(str(call_log))}; return 0 ;;
    "commit -m chore:") printf 'git-commit\\n' >> {shlex.quote(str(call_log))}; return 0 ;;
    *) return 0 ;;
  esac
}}
gh() {{
  if [[ "${{1-}} ${{2-}} ${{3-}}" == "pr comment 201" ]]; then
    printf 'commented\\n' >> {shlex.quote(str(call_log))}
    return 0
  fi
  return 0
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Configure bot git identity" in calls
    assert "Stage follow-up changes" in calls
    assert "Commit follow-up changes" in calls
    assert "push:dependabot/pip/cryptography-43.0.3" in calls
    assert "Comment on PR #201" in calls
    assert "commented" in calls


def test_start_runtime_stack_and_seed_dev_data_builds_images() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
docker() {{
  printf '%s\\n' "$*"
}}
start_runtime_stack_and_seed_dev_data postgres blob-storage app
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "compose up -d --build postgres blob-storage app" in result.stdout
    assert "compose run --rm dev_data" in result.stdout


def test_kill_processes_on_ports_targets_only_listeners() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
declare -f kill_processes_on_ports
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert '-nP -t -iTCP:"$port" -sTCP:LISTEN' in result.stdout


def test_load_pr_context_flattens_multiline_pr_body() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
DEPENDABOT_PR_JSON_FILE="$(mktemp)"
gh() {{
  if [[ "${{1-}} ${{2-}} ${{3-}}" == "pr view 201" ]]; then
    cat <<'EOF'
{{
  "number": 201,
  "title": "Bump cryptography",
  "body": "Line one\\nLine two\\n\\nLine four",
  "url": "https://github.com/scidsg/hushline/pull/201",
  "headRefName": "dependabot/pip/cryptography-43.0.3",
  "baseRefName": "main"
}}
EOF
    return 0
  fi

  return 1
}}
load_pr_context 201
printf '%s\\n%s\\n%s\\n' "$PR_BODY" "$PR_HEAD_REF_NAME" "$PR_BASE_REF_NAME"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "Line one Line two  Line four\n" "dependabot/pip/cryptography-43.0.3\n" "main\n"
    )


def test_main_noop_path_ignores_persisted_run_log_when_deciding_changes(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"
    comment_body = tmp_path / "comment.txt"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
parse_args() {{ :; }}
initialize_run_state() {{
  CHECK_LOG_FILE={shlex.quote(str(tmp_path / "check.log"))}
  PROMPT_FILE={shlex.quote(str(tmp_path / "prompt.txt"))}
  COMMENT_BODY_FILE={shlex.quote(str(comment_body))}
  CODEX_OUTPUT_FILE={shlex.quote(str(tmp_path / "codex-output.txt"))}
  CODEX_TRANSCRIPT_FILE={shlex.quote(str(tmp_path / "codex-transcript.txt"))}
  RUN_LOG_TMP_FILE={shlex.quote(str(tmp_path / "run.log"))}
  DEPENDABOT_PR_JSON_FILE={shlex.quote(str(tmp_path / "pr.json"))}
  RUN_LOG_TIMESTAMP=20260320T000000Z
}}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs() {{ printf '0\\n'; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
select_dependabot_pr() {{
  PR_NUMBER=201
  PR_TITLE="Bump cryptography"
  PR_URL="https://github.com/scidsg/hushline/pull/201"
  PR_BODY="Dependabot body"
  PR_HEAD_REF_NAME="dependabot/pip/cryptography-43.0.3"
  PR_BASE_REF_NAME="main"
  cat > "$DEPENDABOT_PR_JSON_FILE" <<'EOF'
{{"files":[{{"path":"pyproject.toml","additions":1,"deletions":1}}]}}
EOF
}}
configure_bot_git_identity() {{ :; }}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{ :; }}
remote_branch_exists() {{ return 0; }}
build_dependabot_prompt() {{ :; }}
run_codex_from_prompt() {{
  cat > "$CODEX_OUTPUT_FILE" <<'EOF'
No app-side follow-up changes are required.
EOF
}}
run_fix_attempt_loop() {{ return 0; }}
persist_run_log() {{
  RUN_LOG_GIT_PATH="docs/agent-logs/run-20260320T000000Z-dependabot-pr-$1.txt"
  mkdir -p "$REPO_DIR/docs/agent-logs"
  printf 'runner log\\n' > "$REPO_DIR/$RUN_LOG_GIT_PATH"
  printf 'persist:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
has_changes() {{ return 1; }}
docker() {{ :; }}
push_branch_for_pr() {{
  printf 'push:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
git() {{
  local fetch_branch_ref
  fetch_branch_ref=$(
    printf '%s' \
      "fetch origin dependabot/pip/cryptography-43.0.3:refs/remotes/origin/" \
      "dependabot/pip/cryptography-43.0.3"
  )
  case "${{1-}} ${{2-}} ${{3-}}" in
    "fetch origin") return 0 ;;
    "checkout main") return 0 ;;
    "reset --hard origin/main") return 0 ;;
    "clean -fd") return 0 ;;
    "$fetch_branch_ref") return 0 ;;
    "checkout -B dependabot/pip/cryptography-43.0.3") return 0 ;;
    "add -A ") printf 'git-add\\n' >> {shlex.quote(str(call_log))}; return 0 ;;
    "commit -m chore:") printf 'git-commit\\n' >> {shlex.quote(str(call_log))}; return 0 ;;
    *) return 0 ;;
  esac
}}
gh() {{
  if [[ "${{1-}} ${{2-}} ${{3-}}" == "pr comment 201" ]]; then
    printf 'commented\\n' >> {shlex.quote(str(call_log))}
    return 0
  fi
  return 0
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "persist:201" in calls
    assert "Stage follow-up changes" not in calls
    assert "Commit follow-up changes" not in calls
    assert "git-add" not in calls
    assert "git-commit" not in calls
    assert "push:dependabot/pip/cryptography-43.0.3" not in calls
    assert "Comment on PR #201" in calls
    assert "commented" in calls
    assert "did not find any required app-side follow-up changes" in comment_body.read_text(
        encoding="utf-8"
    )
