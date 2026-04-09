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
count_open_bot_prs_excluding_heads() {{ printf '0\\n'; }}
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
    assert "Skipped: coverage already meets target at 100.00%." in result.stdout

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert "Configure bot git identity" in calls
    assert "runtime-bootstrap" in calls
    assert "coverage-scan" in calls
