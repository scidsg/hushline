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
