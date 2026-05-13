from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = ROOT / "scripts" / "agent_daily_coverage_runner.sh"


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


def test_runner_defaults_to_approved_codex_model_and_reasoning() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
printf '%s %s\\n' "$CODEX_MODEL" "$CODEX_REASONING_EFFORT"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "gpt-5.5 high"


def test_coverage_report_summary_text_sorts_and_compresses_ranges(tmp_path: Path) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(
        json.dumps(
            {
                "totals": {"percent_covered": 97.5, "missing_lines": 10},
                "files": {
                    "hushline/alpha.py": {
                        "summary": {"percent_covered": 80.0, "missing_lines": 4},
                        "missing_lines": [10, 11, 12, 18],
                    },
                    "hushline/beta.py": {
                        "summary": {"percent_covered": 70.0, "missing_lines": 6},
                        "missing_lines": [1, 3, 4, 9, 10, 11],
                    },
                    "hushline/full.py": {
                        "summary": {"percent_covered": 100.0, "missing_lines": 0},
                        "missing_lines": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
coverage_report_summary_text {shlex.quote(str(report_path))} 5
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "- hushline/beta.py: 70.00% covered, 6 missing line(s) (1, 3-4, 9-11)"
    assert lines[1] == "- hushline/alpha.py: 80.00% covered, 4 missing line(s) (10-12, 18)"


def test_coverage_target_met_requires_at_least_target() -> None:
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CURRENT_COVERAGE_PERCENT=99.99
COVERAGE_TARGET_PERCENT=100
coverage_target_met
"""

    result = _run_bash(shell_script)

    assert result.returncode == 1

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CURRENT_COVERAGE_PERCENT=100.00
COVERAGE_TARGET_PERCENT=100
coverage_target_met
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr


def test_build_coverage_prompt_warns_against_behavior_changes() -> None:
    coverage_summary = (
        "- hushline/routes/demo.py: 92.00% covered, 4 missing line(s) (10-13)\\n"
        "- hushline/forms/demo.py: 96.00% covered, 3 missing line(s) (20, 24-25)"
    )
    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PROMPT_FILE="$(mktemp)"
CURRENT_COVERAGE_PERCENT="98.25"
COVERAGE_TARGET_PERCENT="100"
CURRENT_COVERAGE_MISSING_LINES="7"
CURRENT_COVERAGE_MISSING_FILES="2"
CURRENT_COVERAGE_SUMMARY=$'{coverage_summary}'
build_coverage_prompt "codex/daily-coverage"
cat "$PROMPT_FILE"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Do not change production behavior just to satisfy coverage." in result.stdout
    assert "Coverage target: 100%." in result.stdout
    assert "human reviewer steps" in result.stdout
    assert "automated checks belong under validation" in result.stdout
    assert "what a human should click, submit, inspect, or verify" in result.stdout


def test_write_pr_body_includes_human_manual_testing_guidance(tmp_path: Path) -> None:
    pr_body_file = tmp_path / "pr-body.md"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
PR_BODY_FILE={shlex.quote(str(pr_body_file))}
COVERAGE_TARGET_PERCENT=100
INITIAL_COVERAGE_PERCENT=99.8
FINAL_COVERAGE_PERCENT=100
CURRENT_COVERAGE_MISSING_LINES=0
CURRENT_COVERAGE_SUMMARY='- No remaining gaps'
stream_changed_files() {{
  printf 'tests/test_settings.py\\n'
}}
write_pr_body \
  "codex/daily-coverage" \
  "main" \
  "docs/agent-logs/run-20260430T000000Z-coverage.txt"
cat "$PR_BODY_FILE"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "## Manual Testing" in result.stdout
    assert "reviewer-executed product checks" in result.stdout
    assert "open the affected feature locally or in staging" in result.stdout
    assert "not applicable beyond automated coverage" not in result.stdout.lower()


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
count_open_human_prs() {{
  printf 'count-open-human-prs\\n' >> {shlex.quote(str(call_log))}
  printf '2\\n'
}}
count_open_bot_prs_excluding_heads() {{
  printf 'count-open-bot-prs\\n' >> {shlex.quote(str(call_log))}
  printf '0\\n'
}}
find_open_pr_for_head_branch() {{ :; }}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: found 2 open human-authored PR(s)." in result.stdout

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "count-open-human-prs" in calls
    assert "count-open-bot-prs" not in calls
    assert "configure-bot-git" not in calls


def test_main_skips_when_coverage_already_meets_target(tmp_path: Path) -> None:
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
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs_excluding_heads() {{ printf '2\\n'; }}
find_open_pr_for_head_branch() {{ :; }}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
remote_branch_exists() {{ return 1; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
run_coverage_scan() {{
  printf 'coverage-scan\\n' >> {shlex.quote(str(call_log))}
  CURRENT_COVERAGE_PERCENT="100.00"
  CURRENT_COVERAGE_MISSING_LINES="0"
  CURRENT_COVERAGE_MISSING_FILES="0"
  CURRENT_COVERAGE_SUMMARY="- No uncovered files remain."
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Open unrelated bot PR count: 2; continuing coverage runner." in result.stdout
    assert "Skipped: coverage already meets target at 100.00%." in result.stdout

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Configure bot git identity" in calls
    assert "runtime-bootstrap" in calls
    assert "coverage-scan" in calls


def test_main_starts_from_base_when_stale_remote_coverage_branch_exists(tmp_path: Path) -> None:
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
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs_excluding_heads() {{ printf '0\\n'; }}
find_open_pr_for_head_branch() {{ :; }}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
remote_branch_exists() {{ return 0; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
run_coverage_scan() {{
  printf 'coverage-scan\\n' >> {shlex.quote(str(call_log))}
  CURRENT_COVERAGE_PERCENT="100.00"
  CURRENT_COVERAGE_MISSING_LINES="0"
  CURRENT_COVERAGE_MISSING_FILES="0"
  CURRENT_COVERAGE_SUMMARY="- No uncovered files remain."
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Create branch codex/daily-coverage" in calls
    assert "Create branch codex/daily-coverage from origin/codex/daily-coverage" not in calls


def test_main_resumes_remote_coverage_branch_when_open_pr_exists(tmp_path: Path) -> None:
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
count_open_human_prs() {{ printf '0\\n'; }}
count_open_bot_prs_excluding_heads() {{ printf '0\\n'; }}
find_open_pr_for_head_branch() {{
  printf '%s\\n' '{{"number":123,"url":"https://example.test/pr/123"}}'
}}
configure_bot_git_identity() {{
  printf 'configure-bot-git\\n' >> {shlex.quote(str(call_log))}
}}
remote_branch_exists() {{ return 0; }}
start_runtime_stack_and_seed_dev_data() {{
  printf 'runtime-bootstrap\\n' >> {shlex.quote(str(call_log))}
}}
run_coverage_scan() {{
  printf 'coverage-scan\\n' >> {shlex.quote(str(call_log))}
  CURRENT_COVERAGE_PERCENT="100.00"
  CURRENT_COVERAGE_MISSING_LINES="0"
  CURRENT_COVERAGE_MISSING_FILES="0"
  CURRENT_COVERAGE_SUMMARY="- No uncovered files remain."
}}
main
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Create branch codex/daily-coverage from origin/codex/daily-coverage" in calls


def test_local_validation_applies_deterministic_lint_fix_for_any_lint_failure(
    tmp_path: Path,
) -> None:
    call_log = tmp_path / "calls.txt"
    check_log = tmp_path / "check.log"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CHECK_LOG_FILE={shlex.quote(str(check_log))}
refresh_runtime_after_schema_changes() {{ :; }}
run_check_capture() {{
  printf '%s\\n' "$1" >> {shlex.quote(str(call_log))}
  case "$1" in
    "Run lint")
      lint_msg='tests/test_notifications.py:297:5: PLR0913 Too many arguments'
      printf '%s\\n' "$lint_msg" >> "$CHECK_LOG_FILE"
      set +e
      return 1
      ;;
    "Auto-fix lint issues (make fix)")
      printf '%s\\n' 'make fix exited non-zero after fixes' >> "$CHECK_LOG_FILE"
      set +e
      return 2
      ;;
    "Re-run lint after deterministic auto-fix")
      printf '%s\\n' 'lint still failing after deterministic fix' >> "$CHECK_LOG_FILE"
      set +e
      return 1
      ;;
  esac
  return 0
}}
run_runtime_check_with_self_heal() {{
  printf 'unexpected-test-run\\n' >> {shlex.quote(str(call_log))}
  return 1
}}
run_coverage_scan() {{
  printf 'unexpected-coverage-run\\n' >> {shlex.quote(str(call_log))}
  return 1
}}
run_local_validation_and_coverage
"""

    result = _run_bash(shell_script)

    assert result.returncode == 1
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert calls == [
        "Run lint",
        "Auto-fix lint issues (make fix)",
        "Re-run lint after deterministic auto-fix",
    ]
    assert "make fix exited non-zero" in result.stdout


def test_coverage_attempt_loop_continues_after_initial_codex_failure(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    check_log = tmp_path / "check.log"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CHECK_LOG_FILE={shlex.quote(str(check_log))}
MAX_COVERAGE_ATTEMPTS=2
MAX_FIX_ATTEMPTS=1
CODEX_CALLS=0
run_codex_from_prompt() {{
  CODEX_CALLS=$((CODEX_CALLS + 1))
  printf 'codex-%s\\n' "$CODEX_CALLS" >> {shlex.quote(str(call_log))}
  if (( CODEX_CALLS == 1 )); then
    set +e
    return 1
  fi
  return 0
}}
has_non_log_changes() {{
  (( CODEX_CALLS >= 2 ))
}}
emit_codex_no_change_diagnostic() {{
  printf 'no-change-%s\\n' "$1" >> {shlex.quote(str(call_log))}
}}
run_local_validation_and_coverage() {{
  printf 'validate\\n' >> {shlex.quote(str(call_log))}
  CURRENT_COVERAGE_PERCENT=100.00
  return 0
}}
run_coverage_attempt_loop
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Warning: Codex coverage attempt 1 failed" in result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert calls == ["codex-1", "codex-2", "validate"]


def test_local_validation_applies_deterministic_fix_before_retrying_tests(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    check_log = tmp_path / "check.log"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CHECK_LOG_FILE={shlex.quote(str(check_log))}
refresh_runtime_after_schema_changes() {{ :; }}
run_check_capture() {{
  printf 'check:%s\\n' "$1" >> {shlex.quote(str(call_log))}
  if [[ "$1" == "Auto-fix lint issues (make fix)" ]]; then
    printf 'make fix exited non-zero after deterministic changes\\n' >> "$CHECK_LOG_FILE"
    set +e
    return 2
  fi
  return 0
}}
run_runtime_check_with_self_heal() {{
  printf 'runtime:%s\\n' "$1" >> {shlex.quote(str(call_log))}
  if [[ "$1" == "Run test (full suite)" ]] || \
    [[ "$1" == "Re-run test after deterministic auto-fix" ]]; then
    printf 'test failure for %s\\n' "$1" >> "$CHECK_LOG_FILE"
    set +e
    return 1
  fi
  return 0
}}
run_coverage_scan() {{
  printf 'unexpected-coverage-run\\n' >> {shlex.quote(str(call_log))}
  return 1
}}
run_local_validation_and_coverage
"""

    result = _run_bash(shell_script)

    assert result.returncode == 1
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert calls == [
        "check:Run lint",
        "runtime:Run test (full suite)",
        "check:Auto-fix lint issues (make fix)",
        "runtime:Re-run test after deterministic auto-fix",
    ]
    assert "tests still failed; applying deterministic fixes before Codex" in result.stdout


def test_coverage_attempt_loop_continues_after_fix_codex_failure(tmp_path: Path) -> None:
    call_log = tmp_path / "calls.txt"
    check_log = tmp_path / "check.log"

    shell_script = f"""
source {shlex.quote(str(RUNNER_SCRIPT))}
CHECK_LOG_FILE={shlex.quote(str(check_log))}
MAX_COVERAGE_ATTEMPTS=1
MAX_FIX_ATTEMPTS=2
CODEX_CALLS=0
VALIDATION_CALLS=0
run_codex_from_prompt() {{
  CODEX_CALLS=$((CODEX_CALLS + 1))
  printf 'codex-%s\\n' "$CODEX_CALLS" >> {shlex.quote(str(call_log))}
  if (( CODEX_CALLS == 2 )); then
    set +e
    return 1
  fi
  return 0
}}
has_non_log_changes() {{ return 0; }}
run_local_validation_and_coverage() {{
  VALIDATION_CALLS=$((VALIDATION_CALLS + 1))
  printf 'validate-%s\\n' "$VALIDATION_CALLS" >> {shlex.quote(str(call_log))}
  if (( VALIDATION_CALLS == 1 )); then
    printf 'lint failed\\n' > "$CHECK_LOG_FILE"
    set +e
    return 1
  fi
  CURRENT_COVERAGE_PERCENT=100.00
  return 0
}}
recent_failure_block_from_text() {{ printf 'lint failed\\n'; }}
failure_signature_from_text() {{ printf 'lint failed\\n'; }}
build_fix_prompt() {{
  printf 'build-fix-prompt\\n' >> {shlex.quote(str(call_log))}
}}
run_coverage_attempt_loop
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Warning: Codex validation self-heal attempt 1 failed" in result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert calls == ["codex-1", "validate-1", "build-fix-prompt", "codex-2", "validate-2"]
