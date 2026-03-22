from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = ROOT / "scripts" / "agent_daily_issue_runner.sh"


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


def test_main_exits_before_runtime_bootstrap_when_bot_pr_exists(tmp_path: Path) -> None:
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
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
resolve_issue_parent_epic() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
count_open_bot_prs() {{
  printf 'count-open-bot-prs\\n' >> {shlex.quote(str(call_log))}
  printf '1\\n'
}}
count_open_human_prs() {{
  printf 'count-open-human-prs\\n' >> {shlex.quote(str(call_log))}
  printf '0\\n'
}}
collect_issue_candidates() {{
  printf 'collect-issue-candidates\\n' >> {shlex.quote(str(call_log))}
  printf '1558\\n'
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: found 1 open PR(s) by hushline-dev." in result.stdout

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "collect-issue-candidates" in calls
    assert "count-open-human-prs" in calls
    assert "count-open-bot-prs" in calls
    assert "configure-bot-git" not in calls
    assert "runtime-bootstrap" not in calls


def test_main_exits_before_runtime_bootstrap_when_human_pr_exists(tmp_path: Path) -> None:
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
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
resolve_issue_parent_epic() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
count_open_bot_prs() {{
  printf 'count-open-bot-prs\\n' >> {shlex.quote(str(call_log))}
  printf '0\\n'
}}
count_open_human_prs() {{
  printf 'count-open-human-prs\\n' >> {shlex.quote(str(call_log))}
  printf '2\\n'
}}
collect_issue_candidates() {{
  printf 'collect-issue-candidates\\n' >> {shlex.quote(str(call_log))}
  printf '1558\\n'
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: found 2 open human-authored PR(s)." in result.stdout

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "collect-issue-candidates" in calls
    assert "count-open-human-prs" in calls
    assert "count-open-bot-prs" not in calls
    assert "configure-bot-git" not in calls
    assert "runtime-bootstrap" not in calls


def test_main_exits_before_runtime_bootstrap_when_no_issue_is_available(tmp_path: Path) -> None:
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
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
resolve_issue_parent_epic() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
count_open_bot_prs() {{
  printf 'count-open-bot-prs\\n' >> {shlex.quote(str(call_log))}
  printf '0\\n'
}}
count_open_human_prs() {{
  printf 'count-open-human-prs\\n' >> {shlex.quote(str(call_log))}
  printf '0\\n'
}}
collect_issue_candidates() {{
  printf 'collect-issue-candidates\\n' >> {shlex.quote(str(call_log))}
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: no open issues found in project" in result.stdout

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "collect-issue-candidates" in calls
    assert "count-open-bot-prs" not in calls
    assert "count-open-human-prs" not in calls
    assert "configure-bot-git" not in calls
    assert "runtime-bootstrap" not in calls


def test_main_bootstrap_does_not_prune_docker_system(tmp_path: Path) -> None:
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
git() {{ :; }}
docker() {{ :; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
configure_bot_git_identity() {{ :; }}
resolve_issue_parent_epic() {{ :; }}
count_open_bot_prs() {{ printf '0\\n'; }}
count_open_human_prs() {{ printf '0\\n'; }}
collect_issue_candidates() {{ printf '1558\\n'; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
  exit 0
}}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Prune Docker system" not in calls
    assert calls[-5:] == [
        "Configure bot git identity",
        "Stop and remove Docker resources",
        "Kill all Docker containers",
        "Kill processes on runner ports",
        "runtime-bootstrap",
    ]


def test_build_pr_title_omits_codex_daily_prefix() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
build_pr_title 1622 $'Normalize geography\\nacross directory listing types'
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "#1622 Normalize geography across directory listing types\n"
    assert "Codex Daily:" not in result.stdout


def test_build_branch_name_uses_issue_prefix() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
build_branch_name 1732
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "codex/daily-issue-1732\n"


def test_build_epic_branch_name_uses_epic_prefix() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
build_epic_branch_name 1735
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "codex/epic-1735\n"


def test_ensure_worktree_on_branch_checks_out_expected_branch() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CURRENT_BRANCH=main
git() {{
  case "${{1-}} ${{2-}} ${{3-}} ${{4-}}" in
    "symbolic-ref --quiet --short HEAD")
      printf '%s\\n' "$CURRENT_BRANCH"
      return 0
      ;;
    "checkout codex/daily-issue-1732  ")
      CURRENT_BRANCH=codex/daily-issue-1732
      return 0
      ;;
  esac
  return 1
}}
ensure_worktree_on_branch codex/daily-issue-1732
printf 'branch=%s\\n' "$CURRENT_BRANCH"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "branch=codex/daily-issue-1732" in result.stdout


def test_ensure_head_commit_on_branch_moves_issue_branch_and_repairs_main() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CURRENT_BRANCH=main
ISSUE_BRANCH_REF=old-issue-ref
MAIN_BRANCH_REF=old-main-ref
git() {{
  case "${{1-}} ${{2-}} ${{3-}} ${{4-}} ${{5-}}" in
    "symbolic-ref --quiet --short HEAD ")
      printf '%s\\n' "$CURRENT_BRANCH"
      return 0
      ;;
    "rev-parse HEAD   ")
      printf 'deadbeef\\n'
      return 0
      ;;
    "branch -f codex/daily-issue-1732 deadbeef ")
      ISSUE_BRANCH_REF=deadbeef
      return 0
      ;;
    "checkout codex/daily-issue-1732   ")
      CURRENT_BRANCH=codex/daily-issue-1732
      return 0
      ;;
    "show-ref --verify --quiet refs/remotes/origin/main ")
      return 0
      ;;
    "branch -f main origin/main ")
      MAIN_BRANCH_REF=origin/main
      return 0
      ;;
  esac
  return 1
}}
ensure_head_commit_on_branch codex/daily-issue-1732 main
printf 'current=%s\\nissue=%s\\nmain=%s\\n' "$CURRENT_BRANCH" "$ISSUE_BRANCH_REF" "$MAIN_BRANCH_REF"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "current=codex/daily-issue-1732" in result.stdout
    assert "issue=deadbeef" in result.stdout
    assert "main=origin/main" in result.stdout


def test_require_branch_has_unique_commits_blocks_empty_pr_branch() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
git() {{
  if [[ "${{1-}} ${{2-}} ${{3-}}" == "rev-list --count main..codex/daily-issue-1732" ]]; then
    printf '0\\n'
    return 0
  fi
  return 1
}}
set +e
require_branch_has_unique_commits main codex/daily-issue-1732
rc=$?
set -e
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "rc=1\n"
    assert (
        "Blocked: branch 'codex/daily-issue-1732' has no commits ahead of 'main';" in result.stderr
    )


def test_resolve_issue_parent_epic_outputs_parent_metadata() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
gh() {{
  cat <<'EOF'
{{"data":{{"repository":{{"issue":{{"parent":{{"number":1735,"title":"Epic title","url":"https://github.com/scidsg/hushline/issues/1735"}}}}}}}}}}
EOF
}}
resolve_issue_parent_epic 1732
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1735\tEpic title\thttps://github.com/scidsg/hushline/issues/1735\n"


def test_resolve_issue_parent_epic_passes_issue_number_as_graphql_int() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
gh() {{
  local saw_graphql=0
  local saw_issue_number=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      graphql)
        saw_graphql=1
        ;;
      -F)
        shift
        if [[ "${{1-}}" == "issueNumber=1732" ]]; then
          saw_issue_number=1
        fi
        ;;
    esac
    shift || break
  done

  if (( saw_graphql == 1 && saw_issue_number == 1 )); then
    cat <<'EOF'
{{"data":{{"repository":{{"issue":{{"parent":{{"number":1735,"title":"Epic title","url":"https://github.com/scidsg/hushline/issues/1735"}}}}}}}}}}
EOF
    return 0
  fi

  return 1
}}
resolve_issue_parent_epic 1732
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1735\tEpic title\thttps://github.com/scidsg/hushline/issues/1735\n"


def test_resolve_project_status_edit_args_outputs_project_field_and_option_ids() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
gh() {{
  cat <<'EOF'
{{
  "data": {{
    "organization": {{
      "projectV2": {{
        "id": "PVT_project",
        "fields": {{
          "nodes": [
            {{
              "id": "PVTSSF_status",
              "name": "Status",
              "options": [
                {{"id": "opt_todo", "name": "Todo"}},
                {{"id": "opt_in_progress", "name": "In Progress"}},
                {{"id": "opt_ready", "name": "Ready for Review"}}
              ]
            }}
          ]
        }}
      }}
    }}
  }}
}}
EOF
}}
resolve_project_status_edit_args 7 "Ready for Review"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PVT_project\tPVTSSF_status\topt_ready\n"


def test_resolve_issue_project_item_id_outputs_matching_project_item() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
gh() {{
  cat <<'EOF'
{{"data":{{"repository":{{"issue":{{"projectItems":{{"nodes":[{{"id":"PVTI_other","project":{{"number":8}}}},{{"id":"PVTI_target","project":{{"number":7}}}}]}}}}}}}}}}
EOF
}}
resolve_issue_project_item_id 1732 7
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PVTI_target"


def test_set_issue_project_status_uses_graphql_mutation() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
resolve_project_number() {{ printf '7\\n'; }}
resolve_project_status_edit_args() {{ printf 'PVT_project\\tPVTSSF_status\\topt_ready\\n'; }}
resolve_issue_project_item_id() {{ printf 'PVTI_target\\n'; }}
gh() {{
  local saw_graphql=0
  local project_id=""
  local item_id=""
  local field_id=""
  local option_id=""
  local query_text=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      api)
        ;;
      graphql)
        saw_graphql=1
        ;;
      -f)
        case "$2" in
          projectId=*) project_id="${{2#projectId=}}" ;;
          itemId=*) item_id="${{2#itemId=}}" ;;
          fieldId=*) field_id="${{2#fieldId=}}" ;;
          optionId=*) option_id="${{2#optionId=}}" ;;
          query=*) query_text="${{2#query=}}" ;;
        esac
        shift
        ;;
    esac
    shift || break
  done

  [[ "$saw_graphql" == "1" ]]
  [[ "$project_id" == "PVT_project" ]]
  [[ "$item_id" == "PVTI_target" ]]
  [[ "$field_id" == "PVTSSF_status" ]]
  [[ "$option_id" == "opt_ready" ]]
  [[ "$query_text" == *"updateProjectV2ItemFieldValue"* ]]
}}
set_issue_project_status 1732 "Ready for Review"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr


def test_collect_issue_candidates_from_project_filters_open_issues_in_target_status() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PROJECT_OWNER=scidsg
PROJECT_COLUMN="Agent Eligible"
PROJECT_STATUS_FIELD_NAME=Status
PROJECT_ITEM_LIMIT=200
REPO_SLUG=scidsg/hushline
gh() {{
  cat <<'EOF'
{{
  "data": {{
    "organization": {{
      "projectV2": {{
        "items": {{
          "nodes": [
            {{
              "fieldValueByName": {{"name": "Agent Eligible"}},
              "content": {{
                "type": "Issue",
                "number": 1558,
                "state": "OPEN",
                "url": "https://github.com/scidsg/hushline/issues/1558",
                "repository": {{"owner": {{"login": "scidsg"}}, "name": "hushline"}}
              }}
            }},
            {{
              "fieldValueByName": {{"name": "Done"}},
              "content": {{
                "type": "Issue",
                "number": 1559,
                "state": "OPEN",
                "url": "https://github.com/scidsg/hushline/issues/1559",
                "repository": {{"owner": {{"login": "scidsg"}}, "name": "hushline"}}
              }}
            }},
            {{
              "fieldValueByName": {{"name": "Agent Eligible"}},
              "content": {{
                "type": "Issue",
                "number": 1560,
                "state": "CLOSED",
                "url": "https://github.com/scidsg/hushline/issues/1560",
                "repository": {{"owner": {{"login": "scidsg"}}, "name": "hushline"}}
              }}
            }},
            {{
              "fieldValueByName": {{"name": "Agent Eligible"}},
              "content": {{
                "type": "Issue",
                "number": 2001,
                "state": "OPEN",
                "url": "https://github.com/other/repo/issues/2001",
                "repository": {{"owner": {{"login": "other"}}, "name": "repo"}}
              }}
            }}
          ]
        }}
      }}
    }}
  }}
}}
EOF
}}
collect_issue_candidates_from_project 12
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1558\n"


def test_collect_issue_candidates_from_project_paginates_before_filtering() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PROJECT_OWNER=scidsg
PROJECT_COLUMN="Agent Eligible"
PROJECT_STATUS_FIELD_NAME=Status
PROJECT_ITEM_LIMIT=5
REPO_SLUG=scidsg/hushline
gh() {{
  local cursor=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -f)
        case "$2" in
          cursor=*) cursor="${{2#cursor=}}" ;;
        esac
        shift
        ;;
    esac
    shift || break
  done

  if [[ -z "$cursor" ]]; then
    cat <<'EOF'
{{
  "data": {{
    "organization": {{
      "projectV2": {{
        "items": {{
          "nodes": [
            {{
              "fieldValueByName": {{"name": "Done"}},
              "content": {{
                "type": "Issue",
                "number": 1559,
                "state": "OPEN",
                "url": "https://github.com/scidsg/hushline/issues/1559",
                "repository": {{"owner": {{"login": "scidsg"}}, "name": "hushline"}}
              }}
            }}
          ],
          "pageInfo": {{
            "hasNextPage": true,
            "endCursor": "cursor-2"
          }}
        }}
      }}
    }}
  }}
}}
EOF
    return 0
  fi

  cat <<'EOF'
{{
  "data": {{
    "organization": {{
      "projectV2": {{
        "items": {{
          "nodes": [
            {{
              "fieldValueByName": {{"name": "Agent Eligible"}},
              "content": {{
                "type": "Issue",
                "number": 1558,
                "state": "OPEN",
                "url": "https://github.com/scidsg/hushline/issues/1558",
                "repository": {{"owner": {{"login": "scidsg"}}, "name": "hushline"}}
              }}
            }}
          ],
          "pageInfo": {{
            "hasNextPage": false,
            "endCursor": null
          }}
        }}
      }}
    }}
  }}
}}
EOF
}}
collect_issue_candidates_from_project 12
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1558\n"


def test_main_allows_existing_epic_pr_before_runtime_bootstrap(tmp_path: Path) -> None:
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
git() {{ :; }}
docker() {{ :; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
collect_issue_candidates() {{ printf '1732\\n'; }}
resolve_issue_parent_epic() {{
  printf '1735\\tEpic title\\thttps://github.com/scidsg/hushline/issues/1735\\n'
}}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs_excluding_heads() {{
  printf 'count-open-bot-prs-excluding-heads\\n' >> {shlex.quote(str(call_log))}
  printf '0\\n'
}}
find_open_pr_for_head_branch() {{
  if [[ "$1" == "codex/epic-1735" ]]; then
    printf '%s\\n' \
      '{{"number":1742,"url":"https://github.com/scidsg/hushline/pull/1742","title":"#1735 Epic"}}'
  fi
}}
configure_bot_git_identity() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
  exit 0
}}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Epic branch codex/epic-1735 already has an open PR to main" in result.stdout
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "count-open-bot-prs-excluding-heads" in calls
    assert "runtime-bootstrap" in calls


def test_main_marks_issue_in_progress_before_runtime_bootstrap(tmp_path: Path) -> None:
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
git() {{ :; }}
docker() {{ :; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
collect_issue_candidates() {{ printf '1558\\n'; }}
resolve_issue_parent_epic() {{ :; }}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs() {{ printf '0\\n'; }}
set_issue_project_status() {{
  printf 'status:%s:%s\\n' "$1" "$2" >> {shlex.quote(str(call_log))}
}}
configure_bot_git_identity() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
  exit 0
}}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Mark issue #1558 as In Progress" in calls
    assert "status:1558:In Progress" in calls
    assert calls.index("Mark issue #1558 as In Progress") < calls.index("runtime-bootstrap")


def test_main_uses_fetched_origin_epic_ref_for_child_pr_uniqueness_check(
    tmp_path: Path,
) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
RUN_LOG_GIT_PATH="docs/agent-logs/run-test-issue-1732.txt"
RUN_LOG_TMP_FILE={shlex.quote(str(tmp_path / "run.log"))}
PR_BODY_FILE={shlex.quote(str(tmp_path / "pr-body.md"))}
parse_args() {{ :; }}
initialize_run_state() {{ :; }}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
git() {{
  case "${{1-}} ${{2-}} ${{3-}} ${{4-}} ${{5-}}" in
    "fetch origin codex/epic-1735:refs/remotes/origin/codex/epic-1735  ")
      return 0
      ;;
    "checkout -B codex/daily-issue-1732 origin/codex/epic-1735 ")
      return 0
      ;;
    "symbolic-ref --quiet --short HEAD ")
      printf 'codex/daily-issue-1732\\n'
      return 0
      ;;
    "diff --cached --quiet  ")
      return 1
      ;;
    "rev-list --count origin/codex/epic-1735..codex/daily-issue-1732  ")
      printf '1\\n'
      printf 'rev-list:%s\\n' \
        "origin/codex/epic-1735..codex/daily-issue-1732" \
        >> {shlex.quote(str(call_log))}
      return 0
      ;;
  esac
  return 0
}}
docker() {{ :; }}
collect_issue_candidates() {{ printf '1732\\n'; }}
resolve_issue_parent_epic() {{
  printf '1735\\tEpic title\\thttps://github.com/scidsg/hushline/issues/1735\\n'
}}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs_excluding_heads() {{ printf '0\\n'; }}
find_open_pr_for_head_branch() {{ :; }}
set_issue_project_status() {{ :; }}
configure_bot_git_identity() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{ :; }}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
remote_branch_exists() {{
  [[ "$1" == "codex/epic-1735" ]]
}}
build_issue_prompt() {{ :; }}
run_issue_attempt_loop() {{ :; }}
persist_run_log() {{
  RUN_LOG_GIT_PATH="docs/agent-logs/run-test-issue-$1.txt"
}}
push_branch_for_pr() {{
  printf 'push:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
write_pr_body() {{ :; }}
build_pr_title() {{
  printf '#1732 Title\\n'
}}
gh() {{
  if [[ "${{1-}} ${{2-}} ${{3-}}" == "issue view 1732" ]]; then
    local last_arg="${{@: -1}}"
    case "$last_arg" in
      .title) printf 'Title\\n' ;;
      .body) printf 'Body\\n' ;;
      .url) printf 'https://github.com/scidsg/hushline/issues/1732\\n' ;;
      '.labels[].name // empty') printf '\\n' ;;
    esac
    return 0
  fi
  if [[ "${{1-}} ${{2-}}" == "pr create" ]]; then
    printf 'https://github.com/scidsg/hushline/pull/2001\\n'
    return 0
  fi
  return 0
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "rev-list:origin/codex/epic-1735..codex/daily-issue-1732" in calls
    assert "push:codex/daily-issue-1732" in calls


def test_write_pr_body_for_child_issue_references_epic_and_closes_child_issue(
    tmp_path: Path,
) -> None:
    pr_body_file = tmp_path / "pr-body.md"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PR_BODY_FILE={shlex.quote(str(pr_body_file))}
stream_changed_files() {{
  printf 'scripts/agent_daily_issue_runner.sh\\n'
}}
count_non_log_changed_files() {{
  printf '1\\n'
}}
summarize_non_log_changed_areas() {{
  printf 'scripts\\n'
}}
summarize_non_log_changed_work() {{
  printf 'runner orchestration\\n'
}}
write_pr_body \
  1732 \
  "Profile settings forms" \
  "https://github.com/scidsg/hushline/issues/1732" \
  "codex/daily-issue-1732" \
  "codex/epic-1735" \
  "" \
  "docs/agent-logs/run-20260318T000000Z-issue-1732.txt" \
  1735 \
  "WTForms modernization" \
  "https://github.com/scidsg/hushline/issues/1735"
cat "$PR_BODY_FILE"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "This PR implements child issue #1732" in result.stdout
    assert "Linked issue: #1732" in result.stdout
    assert "Closes #1732" not in result.stdout
    assert "Closes #1735" not in result.stdout
    assert "- Epic: https://github.com/scidsg/hushline/issues/1735" in result.stdout
    assert "- Child issue: https://github.com/scidsg/hushline/issues/1732" in result.stdout
    assert "- Base branch: codex/epic-1735" in result.stdout


def test_main_marks_issue_ready_for_review_after_opening_pr(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    repo_dir = tmp_path / "repo"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
mkdir -p "$REPO_DIR/.git"
RUN_LOG_GIT_PATH="docs/agent-logs/run-test-issue-1558.txt"
RUN_LOG_TMP_FILE={shlex.quote(str(tmp_path / "run.log"))}
PR_BODY_FILE={shlex.quote(str(tmp_path / "pr-body.md"))}
parse_args() {{ :; }}
initialize_run_state() {{ :; }}
cleanup() {{ :; }}
require_cmd() {{ :; }}
require_positive_integer() {{ :; }}
run_step() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  shift
  "$@"
}}
    git() {{
      case "${{1-}} ${{2-}} ${{3-}} ${{4-}} ${{5-}}" in
        "symbolic-ref --quiet --short HEAD ")
          printf 'codex/daily-issue-1558\\n'
          return 0
          ;;
        "rev-list --count main..codex/daily-issue-1558  ")
          printf '1\\n'
          return 0
          ;;
        "diff --cached --quiet  ")
          return 1
          ;;
        "checkout codex/daily-issue-1558   ")
          return 0
          ;;
      esac
      return 0
    }}
docker() {{ :; }}
collect_issue_candidates() {{ printf '1558\\n'; }}
resolve_issue_parent_epic() {{ :; }}
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs() {{ printf '0\\n'; }}
set_issue_project_status() {{
  printf 'status:%s:%s\\n' "$1" "$2" >> {shlex.quote(str(call_log))}
}}
configure_bot_git_identity() {{ :; }}
start_runtime_stack_and_seed_dev_data() {{ :; }}
kill_all_docker_containers() {{ :; }}
kill_processes_on_ports() {{ :; }}
remote_branch_exists() {{ return 1; }}
build_issue_prompt() {{ :; }}
run_issue_attempt_loop() {{ :; }}
persist_run_log() {{
  RUN_LOG_GIT_PATH="docs/agent-logs/run-test-issue-$1.txt"
  printf 'persist:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
push_branch_for_pr() {{
  printf 'push:%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
write_pr_body() {{
  printf 'pr-body:%s:%s\\n' "$1" "$5" >> {shlex.quote(str(call_log))}
}}
build_pr_title() {{
  printf '#1558 Title\\n'
}}
gh() {{
  if [[ "${{1-}} ${{2-}} ${{3-}}" == "issue view 1558" ]]; then
    local last_arg="${{@: -1}}"
    case "$last_arg" in
      .title) printf 'Title\\n' ;;
      .body) printf 'Body\\n' ;;
      .url) printf 'https://github.com/scidsg/hushline/issues/1558\\n' ;;
      '.labels[].name // empty') printf '\\n' ;;
    esac
    return 0
  fi
  if [[ "${{1-}} ${{2-}}" == "pr create" ]]; then
    printf 'https://github.com/scidsg/hushline/pull/2000\\n'
    return 0
  fi
  return 0
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "status:1558:In Progress" in calls
    assert "status:1558:Ready for Review" in calls
    assert calls.index("status:1558:Ready for Review") > calls.index("push:codex/daily-issue-1558")


def test_persisted_runner_log_excludes_codex_transcript(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    prompt_file = tmp_path / "prompt.txt"
    output_file = tmp_path / "codex-output.txt"
    transcript_file = tmp_path / "codex-transcript.txt"
    run_log_file = tmp_path / "run-log.txt"
    console_file = tmp_path / "console.txt"

    repo_dir.mkdir()
    prompt_file.write_text("issue prompt\n", encoding="utf-8")

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
PROMPT_FILE={shlex.quote(str(prompt_file))}
CODEX_OUTPUT_FILE={shlex.quote(str(output_file))}
CODEX_TRANSCRIPT_FILE={shlex.quote(str(transcript_file))}
RUN_LOG_TMP_FILE={shlex.quote(str(run_log_file))}
RUN_LOG_TIMESTAMP=20260308T000000Z
RUN_LOG_RETENTION_COUNT=10
RUN_LOG_GIT_PATH=""
REPO_SLUG=scidsg/hushline
CODEX_MODEL=test-model
CODEX_REASONING_EFFORT=high
VERBOSE_CODEX_OUTPUT=0
exec 3>{shlex.quote(str(console_file))}
codex() {{
  if [[ "$1" != "exec" ]]; then
    return 9
  fi
  printf 'SECRET_TRANSCRIPT_LINE\\n'
  printf 'Safe final summary\\n' > "$CODEX_OUTPUT_FILE"
}}
run_codex_from_prompt > "$RUN_LOG_TMP_FILE" 2>&1
persist_run_log 1556
printf '%s\\n' "$RUN_LOG_GIT_PATH"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr

    persisted_log = repo_dir / result.stdout.strip()
    assert persisted_log.exists()
    assert "SECRET_TRANSCRIPT_LINE" in transcript_file.read_text(encoding="utf-8")
    assert "SECRET_TRANSCRIPT_LINE" not in run_log_file.read_text(encoding="utf-8")
    assert "SECRET_TRANSCRIPT_LINE" not in persisted_log.read_text(encoding="utf-8")
    assert "Safe final summary" in persisted_log.read_text(encoding="utf-8")
    assert console_file.read_text(encoding="utf-8") == ""


def test_persisted_runner_log_redacts_developer_metadata(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    run_log_file = tmp_path / "run-log.txt"

    repo_dir.mkdir()
    run_log_file.write_text(
        "\n".join(
            [
                "Runner Codex config: model=gpt-5.4 reasoning_effort=high verbose_codex_output=0",
                "Configured git identity: hushline-dev <git-dev@scidsg.org>",
                "Run log file: /Users/scidsg/hushline/docs/agent-logs/run.log",
                "Global log file: /Users/scidsg/.codex/logs/hushline-agent-runner.log",
                "workdir: /Users/scidsg/hushline",
                "model: gpt-5.4",
                "provider: openai",
                "approval: never",
                "sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/scidsg/.codex/memories]",
                "reasoning effort: high",
                "reasoning summaries: none",
                "session id: 019ccba0-3d52-7271-93de-106986a70c42",
                "Home path: /Users/scidsg/hushline",
                "Email: hello@example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(repo_dir))}
RUN_LOG_TMP_FILE={shlex.quote(str(run_log_file))}
RUN_LOG_TIMESTAMP=20260308T000000Z
RUN_LOG_RETENTION_COUNT=10
RUN_LOG_GIT_PATH=""
REPO_SLUG=scidsg/hushline
persist_run_log 1556
printf '%s\\n' "$RUN_LOG_GIT_PATH"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr

    persisted_log = repo_dir / result.stdout.strip()
    persisted_text = persisted_log.read_text(encoding="utf-8")

    assert persisted_log.exists()
    assert "git-dev@scidsg.org" not in persisted_text
    assert "hello@example.com" not in persisted_text
    assert "/Users/scidsg" not in persisted_text
    assert "Runner Codex config: [redacted]" in persisted_text
    assert "Configured git identity: [redacted]" in persisted_text
    assert "Run log file: [redacted]" in persisted_text
    assert "Global log file: [redacted]" in persisted_text
    assert "workdir: [redacted]" in persisted_text
    assert "model: [redacted]" in persisted_text
    assert "provider: [redacted]" in persisted_text
    assert "approval: [redacted]" in persisted_text
    assert "sandbox: [redacted]" in persisted_text
    assert "reasoning effort: [redacted]" in persisted_text
    assert "reasoning summaries: [redacted]" in persisted_text
    assert "session id: [redacted]" in persisted_text
    assert "Home path: [redacted-path]" in persisted_text
    assert "Email: [redacted-email]" in persisted_text


def test_verbose_codex_output_streams_to_console_only(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    output_file = tmp_path / "codex-output.txt"
    transcript_file = tmp_path / "codex-transcript.txt"
    run_log_file = tmp_path / "run-log.txt"
    console_file = tmp_path / "console.txt"

    prompt_file.write_text("issue prompt\n", encoding="utf-8")

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR={shlex.quote(str(tmp_path))}
PROMPT_FILE={shlex.quote(str(prompt_file))}
CODEX_OUTPUT_FILE={shlex.quote(str(output_file))}
CODEX_TRANSCRIPT_FILE={shlex.quote(str(transcript_file))}
CODEX_MODEL=test-model
CODEX_REASONING_EFFORT=high
VERBOSE_CODEX_OUTPUT=1
exec 3>{shlex.quote(str(console_file))}
codex() {{
  if [[ "$1" != "exec" ]]; then
    return 9
  fi
  printf 'VERBOSE_TRANSCRIPT_LINE\\n'
  printf 'Safe final summary\\n' > "$CODEX_OUTPUT_FILE"
}}
run_codex_from_prompt > {shlex.quote(str(run_log_file))} 2>&1
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr

    transcript_text = transcript_file.read_text(encoding="utf-8")
    run_log_text = run_log_file.read_text(encoding="utf-8")
    console_text = console_file.read_text(encoding="utf-8")

    assert "VERBOSE_TRANSCRIPT_LINE" in transcript_text
    assert "VERBOSE_TRANSCRIPT_LINE" in console_text
    assert "VERBOSE_TRANSCRIPT_LINE" not in run_log_text
    assert "Safe final summary" in run_log_text


def test_write_pr_narrative_lead_adds_plain_language_summary() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
stream_changed_files() {{
  printf '%s\\n' \
    'hushline/model/directory.py' \
    'hushline/routes/directory.py' \
    'tests/test_directory.py' \
    'docs/agent-logs/run-20260308T000000Z-issue-1622.txt'
}}
write_pr_narrative_lead \
  1622 \
  "Normalize geography across directory listing types"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert (
        'This PR addresses the issue "Normalize geography across '
        'directory listing types" by updating data and model code in `hushline/model`, '
        "request-handling code in `hushline/routes`, and automated tests in "
        "`tests/test_directory.py`."
    ) in result.stdout
    assert (
        "The change includes both implementation work and automated tests, showing the "
        "intended behavior and how it is verified."
    ) in result.stdout
    assert (
        "It touches 3 non-log file(s) (4 total including runner artifacts), primarily "
        "in hushline/model, hushline/routes, and tests/test_directory.py."
    ) in result.stdout


def test_write_pr_narrative_lead_explains_log_only_run() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
stream_changed_files() {{
  printf '%s\\n' 'docs/agent-logs/run-20260308T000000Z-issue-1622.txt'
}}
write_pr_narrative_lead 1622 "Normalize geography across directory listing types"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert (
        "This run does not change the product itself; it only updates the runner log "
        "artifact that records what the daily runner did."
    ) in result.stdout
    assert "This run only changes the runner log artifact." in result.stdout


def test_audit_failure_environmental_classifier_matches_network_errors() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
if audit_failure_looks_environmental "pip failed: temporary failure in name resolution"; then
  printf 'environmental\\n'
else
  printf 'non-environmental\\n'
fi
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "environmental\n"


def test_audit_failure_environmental_classifier_rejects_tls_vulnerability_text() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
audit_output="CVE-2023-1234: TLS certificate validation bypass in dependency"
if audit_failure_looks_environmental "$audit_output"; then
  printf 'environmental\\n'
else
  printf 'non-environmental\\n'
fi
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "non-environmental\n"


def test_runtime_bootstrap_retries_retryable_registry_failure(tmp_path: Path) -> None:
    calls_file = tmp_path / "docker-calls.txt"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
RUNTIME_BOOTSTRAP_ATTEMPTS=3
RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS=1
docker() {{
  printf '%s\\n' "$*" >> {shlex.quote(str(calls_file))}
  if [[ "$1" == "compose" && "$2" == "up" ]]; then
    if [[ $(grep -c '^compose up -d --build$' {shlex.quote(str(calls_file))}) == "1" ]]; then
      printf '%s%s%s%s%s\\n' \
        'Error response from daemon: unknown: failed to resolve reference ' \
        '"docker.io/library/postgres:16.4-alpine3.20": ' \
        'unexpected status from HEAD request to ' \
        'https://registry-1.docker.io/v2/library/postgres/manifests/' \
        '16.4-alpine3.20: 500 Internal Server Error' \
        >&2
      return 1
    fi
    return 0
  fi
  if [[ "$1" == "compose" && "$2" == "run" && "$4" == "dev_data" ]]; then
    return 0
  fi
  if [[ "$1" == "compose" && "$2" == "down" ]]; then
    return 0
  fi
  printf 'unexpected docker invocation: %s\\n' "$*" >&2
  return 99
}}
sleep() {{ :; }}
if start_runtime_stack_and_seed_dev_data --build; then
  rc=0
else
  rc=$?
fi
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "rc=0" in result.stdout
    assert "retryable network/bootstrap failure" in result.stdout

    docker_calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert docker_calls.count("compose up -d --build") == 2
    assert docker_calls.count("compose run --rm dev_data") == 1
    assert "compose down -v --remove-orphans" in docker_calls


def test_runtime_bootstrap_retries_retryable_pypi_dns_failure(tmp_path: Path) -> None:
    calls_file = tmp_path / "docker-calls.txt"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
RUNTIME_BOOTSTRAP_ATTEMPTS=3
RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS=1
docker() {{
  printf '%s\\n' "$*" >> {shlex.quote(str(calls_file))}
  if [[ "$1" == "compose" && "$2" == "up" ]]; then
    if [[ $(grep -c '^compose up -d --build$' {shlex.quote(str(calls_file))}) == "1" ]]; then
      printf '%s\\n' \
        '#13 54.81     | All attempts to connect to files.pythonhosted.org failed.' \
        '#13 54.81     | Probable Causes:' \
        '#13 54.81     |     - the hostname cannot be resolved by your DNS' \
        '#13 54.81     |     - your network is not connected to the internet' \
        'target app: failed to solve: process ' \
        '\"/bin/sh -c poetry install --no-root\" ' \
        'did not complete successfully: exit code: 1' \
        >&2
      return 1
    fi
    return 0
  fi
  if [[ "$1" == "compose" && "$2" == "run" && "$4" == "dev_data" ]]; then
    return 0
  fi
  if [[ "$1" == "compose" && "$2" == "down" ]]; then
    return 0
  fi
  printf 'unexpected docker invocation: %s\\n' "$*" >&2
  return 99
}}
sleep() {{ :; }}
if start_runtime_stack_and_seed_dev_data --build; then
  rc=0
else
  rc=$?
fi
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "rc=0" in result.stdout
    assert "retryable network/bootstrap failure" in result.stdout

    docker_calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert docker_calls.count("compose up -d --build") == 2
    assert docker_calls.count("compose run --rm dev_data") == 1
    assert "compose down -v --remove-orphans" in docker_calls


def test_runtime_bootstrap_does_not_retry_non_retryable_failure(tmp_path: Path) -> None:
    calls_file = tmp_path / "docker-calls.txt"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
RUNTIME_BOOTSTRAP_ATTEMPTS=3
RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS=1
docker() {{
  printf '%s\\n' "$*" >> {shlex.quote(str(calls_file))}
  if [[ "$1" == "compose" && "$2" == "up" ]]; then
    printf 'invalid compose project configuration\\n' >&2
    return 1
  fi
  if [[ "$1" == "compose" && "$2" == "down" ]]; then
    return 0
  fi
  if [[ "$1" == "compose" && "$2" == "run" && "$4" == "dev_data" ]]; then
    return 0
  fi
  printf 'unexpected docker invocation: %s\\n' "$*" >&2
  return 99
}}
sleep() {{ :; }}
if start_runtime_stack_and_seed_dev_data --build; then
  rc=0
else
  rc=$?
fi
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "rc=1" in result.stdout
    assert "retryable network/bootstrap failure" not in result.stdout

    docker_calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert docker_calls.count("compose up -d --build") == 1
    assert "compose down -v --remove-orphans" not in docker_calls
    assert "compose run --rm dev_data" not in docker_calls


def test_runtime_bootstrap_does_not_retry_seed_eoferror(tmp_path: Path) -> None:
    calls_file = tmp_path / "docker-calls.txt"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
RUNTIME_BOOTSTRAP_ATTEMPTS=3
RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS=1
docker() {{
  printf '%s\\n' "$*" >> {shlex.quote(str(calls_file))}
  if [[ "$1" == "compose" && "$2" == "up" ]]; then
    return 0
  fi
  if [[ "$1" == "compose" && "$2" == "run" && "$4" == "dev_data" ]]; then
    printf 'Traceback (most recent call last):\\nEOFError: seed fixture truncated\\n' >&2
    return 1
  fi
  if [[ "$1" == "compose" && "$2" == "down" ]]; then
    return 0
  fi
  printf 'unexpected docker invocation: %s\\n' "$*" >&2
  return 99
}}
sleep() {{ :; }}
if start_runtime_stack_and_seed_dev_data --build; then
  rc=0
else
  rc=$?
fi
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "rc=1" in result.stdout
    assert "retryable network/bootstrap failure" not in result.stdout

    docker_calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert docker_calls.count("compose up -d --build") == 1
    assert docker_calls.count("compose run --rm dev_data") == 1
    assert "compose down -v --remove-orphans" not in docker_calls


def test_resolve_bot_git_signing_key_uses_existing_ssh_git_config(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    shell_script = f"""
repo_dir={shlex.quote(str(repo_dir))}
source {shlex.quote(str(RUNNER_SCRIPT))}
cd "$repo_dir"
BOT_GIT_GPG_FORMAT=ssh
BOT_GIT_SIGNING_KEY=""
DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH=""
git() {{
  if [[ "$1" == "config" && "$2" == "--get" && "$3" == "user.signingkey" ]]; then
    printf '%s\\n' "$repo_dir/.ssh/bot-signing.pub"
    return 0
  fi
  if [[ "$1" == "config" && "$2" == "--get" && "$3" == "gpg.format" ]]; then
    printf 'ssh\\n'
    return 0
  fi
  printf 'unexpected git invocation: %s\\n' "$*" >&2
  return 99
}}
resolve_bot_git_signing_key
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(repo_dir / ".ssh" / "bot-signing.pub")


def test_resolve_bot_git_signing_key_ignores_non_ssh_git_config(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    shell_script = f"""
repo_dir={shlex.quote(str(repo_dir))}
git -C "$repo_dir" init -q
git -C "$repo_dir" config user.signingkey 102783C80AF9335A
source {shlex.quote(str(RUNNER_SCRIPT))}
cd "$repo_dir"
BOT_GIT_GPG_FORMAT=ssh
BOT_GIT_SIGNING_KEY=""
DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH=""
if resolve_bot_git_signing_key; then
  printf 'resolved\\n'
else
  printf 'missing\\n'
fi
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "missing\n"


def test_assert_ssh_signing_ready_does_not_require_local_private_key_file(tmp_path: Path) -> None:
    public_key_file = tmp_path / "bot-signing.pub"
    public_key_file.write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBotSigningKeyExample hushline-dev\n",
        encoding="utf-8",
    )

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
git() {{
  if [[ "$1" == "init" || "$1" == "config" || "$1" == "commit" ]]; then
    return 0
  fi
  printf 'unexpected git invocation: %s\\n' "$*" >&2
  return 99
}}
assert_ssh_signing_ready {shlex.quote(str(public_key_file))}
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr


def test_require_positive_integer_rejects_zero() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
require_positive_integer "HUSHLINE_DAILY_MAX_FIX_ATTEMPTS" "0"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 1
    assert "HUSHLINE_DAILY_MAX_FIX_ATTEMPTS must be a positive integer" in result.stderr


def test_require_positive_integer_rejects_zero_for_runtime_bootstrap_retry_delay() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
require_positive_integer "HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS" "0"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 1
    assert (
        "HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS must be a positive integer"
        in result.stderr
    )


def test_failure_signature_from_text_returns_structured_markers() -> None:
    failure_text = (
        "failure_text=$'FAILED tests/test_example.py\\nAssertionError:\\nTraceback\\n'\\\n"
        "$'tests/test_module.py:12:34: F821 Undefined name `MissingName`\\nError: boom'"
    )
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
{failure_text}
failure_signature_from_text "$failure_text"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "pytest-test-failures",
        "assertion-error",
        "python-traceback",
        "lint-diagnostics",
        "generic-error",
    ]


def test_failure_signature_from_text_falls_back_when_no_marker_matches() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
failure_signature_from_text "totally unmatched output"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "no-structured-signature\n"


def test_build_fix_prompt_withholds_raw_check_output(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    failure_context = (
        "$'tests/test_module.py:12:34: F821 Undefined name `MissingName`\\n"
        "FAILED tests/test_example.py::test_case'"
    )
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PROMPT_FILE={shlex.quote(str(prompt_file))}
build_fix_prompt \
  1558 \
  "Issue title" \
  "branch-name" \
  "status summary" \
  "prior codex output" \
  {failure_context} \
  "generic-error" \
  "2"
cat "$PROMPT_FILE"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Raw failed check output is intentionally withheld" in result.stdout
    assert "---BEGIN CHECK OUTPUT---" not in result.stdout
    assert "---BEGIN FAILURE CONTEXT---" in result.stdout
    assert "FAILED tests/test_example.py::test_case" in result.stdout
    assert "generic-error" in result.stdout
    assert "tests/test_module.py:12:34: F821 Undefined name `MissingName`" in result.stdout
    assert (
        "Use the sanitized recent failure block above as the primary debugging context."
        in result.stdout
    )
    assert "only `make lint` and `make test` locally before opening a PR" in result.stdout


def test_recent_failure_block_from_text_extracts_recent_actionable_context() -> None:
    failure_text = (
        "failure_text=$'Container hushline-dev_data-1 Exited\\n'\\\n"
        "$'tests/test_setup.py::test_boot PASSED [  1%]\\n'\\\n"
        "$'/Users/scidsg/hushline/tests/test_module.py:12:34: "
        "F821 Undefined name `MissingName`\\n'\\\n"
        "$'make: *** [fix] Error 1\\nFAILED tests/test_example.py::test_case\\n"
        "/tmp/codex-secret-artifact.txt\\nTraceback\\n'"
    )
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
REPO_DIR=/Users/scidsg/hushline
{failure_text}
recent_failure_block_from_text "$failure_text"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Container hushline-dev_data-1 Exited" not in result.stdout
    assert "PASSED" not in result.stdout
    assert "/Users/scidsg/hushline" not in result.stdout
    assert "tests/test_module.py:12:34: F821 Undefined name `MissingName`" in result.stdout
    assert "FAILED tests/test_example.py::test_case" in result.stdout
    assert "Traceback" in result.stdout
    assert "make: *** [fix] Error 1" in result.stdout


def test_recent_failure_block_from_text_redacts_secret_like_values() -> None:
    failure_text = (
        "failure_text=$'TOKEN=supersecret123\\n'\\\n"
        "$'authorization: Bearer abc/def+ghi~jkl\\n'\\\n"
        "$'Bearer zyx/wvu+tsr~qpo\\n'\\\n"
        "$'password = hunter2\\n'\\\n"
        "$'FAILED tests/test_example.py::test_case\\n'"
    )
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
{failure_text}
recent_failure_block_from_text "$failure_text"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "TOKEN=[redacted]" in result.stdout
    assert "authorization: Bearer [redacted]" in result.stdout
    assert "Bearer [redacted]" in result.stdout
    assert "password = [redacted]" in result.stdout
    assert "supersecret123" not in result.stdout
    assert "abc/def+ghi~jkl" not in result.stdout
    assert "zyx/wvu+tsr~qpo" not in result.stdout
    assert "hunter2" not in result.stdout


def test_failure_excerpt_from_text_redacts_sensitive_values() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
failure_text=$'AssertionError: token=SECRET123\\n'\
$'E TOKEN=UPPERSECRET456\\n'\
$'E api_key:abcd1234\\n'\
$'E CLIENT_SECRET=topsecret789\\n'\
$'Error: contact security@example.org\\n'\
$'Traceback Authorization: Bearer supersecrettoken\\n'\
$'FAILED tests/test_example.py::test_case\\n'
sanitize_failure_excerpt "$failure_text"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "AssertionError:" in result.stdout
    assert "SECRET123" not in result.stdout
    assert "UPPERSECRET456" not in result.stdout
    assert "abcd1234" not in result.stdout
    assert "topsecret789" not in result.stdout
    assert "security@example.org" not in result.stdout
    assert "supersecrettoken" not in result.stdout
    assert "token=[redacted]" in result.stdout
    assert "TOKEN=[redacted]" in result.stdout
    assert "api_key:[redacted]" in result.stdout
    assert "CLIENT_SECRET=[redacted]" in result.stdout
    assert "[redacted-email]" in result.stdout
    assert "Authorization: Bearer [redacted]" in result.stdout


def test_issue_attempt_loop_stops_after_max_attempts() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
MAX_ISSUE_ATTEMPTS=3
build_issue_prompt() {{ :; }}
run_codex_from_prompt() {{ :; }}
has_changes() {{ return 1; }}
run_fix_attempt_loop() {{ return 0; }}
set +e
run_issue_attempt_loop 1558 "Title" "Body" "" "branch"
rc=$?
set -e
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "rc=1" in result.stdout
    assert "Codex produced no usable changes for issue #1558 after 3 attempt(s)." in result.stderr


def test_fix_attempt_loop_stops_after_max_attempts(tmp_path: Path) -> None:
    check_log_file = tmp_path / "check.log"
    codex_output_file = tmp_path / "codex-output.txt"
    check_log_file.write_text("persistent failure\n", encoding="utf-8")
    codex_output_file.write_text("prior summary\n", encoding="utf-8")

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
MAX_FIX_ATTEMPTS=2
CHECK_LOG_FILE={shlex.quote(str(check_log_file))}
CODEX_OUTPUT_FILE={shlex.quote(str(codex_output_file))}
PREVIOUS_FAILURE_SIGNATURE=""
FAILURE_SIGNATURE=""
REPEATED_FAILURE_COUNT=0
run_local_workflow_checks() {{ return 1; }}
failure_signature_from_text() {{ printf 'same-failure\\n'; }}
current_change_summary() {{ printf 'summary\\n'; }}
build_fix_prompt() {{ :; }}
run_codex_from_prompt() {{ :; }}
set +e
run_fix_attempt_loop 1558 "Title" "Body" "" "branch"
rc=$?
set -e
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "rc=1" in result.stdout
    assert (
        "Blocked: workflow checks failed after 2 self-heal attempt(s) for issue #1558."
        in result.stderr
    )


def test_fix_attempt_loop_does_not_run_extra_post_test_gate(tmp_path: Path) -> None:
    calls_file = tmp_path / "calls.txt"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
run_local_workflow_checks() {{
  printf 'checks\\n' >> {shlex.quote(str(calls_file))}
  return 0
}}
run_test_gap_gate() {{
  printf 'unexpected-test-gap\\n' >> {shlex.quote(str(calls_file))}
  return 1
}}
run_fix_attempt_loop 1558 "Title" "Body" "test-gap" "branch"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert calls_file.read_text(encoding="utf-8").splitlines() == ["checks"]


def test_run_local_workflow_checks_runs_lint_then_test_only(tmp_path: Path) -> None:
    calls_file = tmp_path / "calls.txt"
    check_log_file = tmp_path / "check.log"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CHECK_LOG_FILE={shlex.quote(str(check_log_file))}
refresh_runtime_after_schema_changes() {{ :; }}
run_check_capture() {{
  printf 'capture:%s:%s\\n' "$1" "$2" >> {shlex.quote(str(calls_file))}
  return 0
}}
run_runtime_check_with_self_heal() {{
  printf 'runtime:%s:%s\\n' "$1" "$2" >> {shlex.quote(str(calls_file))}
  return 0
}}
run_local_workflow_checks
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert calls_file.read_text(encoding="utf-8").splitlines() == [
        "capture:Run lint:make",
        "runtime:Run test (full suite):make",
    ]


def test_run_local_workflow_checks_stops_after_non_fixable_lint_failure(
    tmp_path: Path,
) -> None:
    calls_file = tmp_path / "calls.txt"
    check_log_file = tmp_path / "check.log"
    check_log_file.write_text("lint failure\n", encoding="utf-8")

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CHECK_LOG_FILE={shlex.quote(str(check_log_file))}
refresh_runtime_after_schema_changes() {{ :; }}
run_check_capture() {{
  printf 'capture:%s:%s\\n' "$1" "$2" >> {shlex.quote(str(calls_file))}
  return 1
}}
lint_failure_looks_auto_fixable() {{ return 1; }}
auto_fix_lint_with_containerized_tooling() {{
  printf 'autofix\\n' >> {shlex.quote(str(calls_file))}
  return 0
}}
run_runtime_check_with_self_heal() {{
  printf 'runtime:%s:%s\\n' "$1" "$2" >> {shlex.quote(str(calls_file))}
  return 0
}}
set +e
run_local_workflow_checks
rc=$?
set -e
printf 'rc=%s\\n' "$rc"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "rc=1\n"
    assert calls_file.read_text(encoding="utf-8").splitlines() == [
        "capture:Run lint:make",
    ]
