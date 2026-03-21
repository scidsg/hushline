from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_SCRIPT = ROOT / "scripts" / "run_dependabot_pr_queue.sh"


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-lc", script],  # noqa: S603 - controlled test harness invocation
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_queue_runner_defaults_repo_dir_to_checkout_root() -> None:
    shell_script = f"""
source {shlex.quote(str(QUEUE_SCRIPT))}
printf '%s\\n' "$REPO_DIR"
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == ROOT


def test_queue_runner_skips_when_active_lock_exists(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    lock_dir = repo_dir / ".tmp" / "dependabot-pr-runner.lock"
    runner_stub = tmp_path / "runner-stub.sh"
    runner_stub.write_text("#!/usr/bin/env bash\nprintf 'should-not-run\\n'\n", encoding="utf-8")
    runner_stub.chmod(0o755)

    shell_script = f"""
mkdir -p {shlex.quote(str(lock_dir))}
sleep 30 &
lock_pid=$!
trap 'kill "$lock_pid" >/dev/null 2>&1 || true' EXIT
printf '%s\\n' "$lock_pid" > {shlex.quote(str(lock_dir / "pid"))}
HUSHLINE_REPO_DIR={shlex.quote(str(repo_dir))} \
HUSHLINE_DEPENDABOT_QUEUE_LOCK_DIR={shlex.quote(str(lock_dir))} \
HUSHLINE_DEPENDABOT_RUNNER_SCRIPT={shlex.quote(str(runner_stub))} \
{shlex.quote(str(QUEUE_SCRIPT))}
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Skipped: Dependabot queue runner already active" in result.stdout
    assert "should-not-run" not in result.stdout


def test_queue_runner_delegates_to_dependabot_runner_with_args(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    runner_stub = tmp_path / "runner-stub.sh"
    runner_stub.write_text(
        "#!/usr/bin/env bash\n" "printf 'runner:%s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    runner_stub.chmod(0o755)
    lock_dir = repo_dir / ".tmp" / "dependabot-pr-runner.lock"

    shell_script = f"""
mkdir -p {shlex.quote(str(repo_dir))}
HUSHLINE_REPO_DIR={shlex.quote(str(repo_dir))} \
HUSHLINE_DEPENDABOT_QUEUE_LOCK_DIR={shlex.quote(str(lock_dir))} \
HUSHLINE_DEPENDABOT_RUNNER_SCRIPT={shlex.quote(str(runner_stub))} \
{shlex.quote(str(QUEUE_SCRIPT))} --pr 1772
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "runner:--pr 1772" in result.stdout
    assert not lock_dir.exists()


def test_queue_runner_recovers_stale_lock_and_runs(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    lock_dir = repo_dir / ".tmp" / "dependabot-pr-runner.lock"
    runner_stub = tmp_path / "runner-stub.sh"
    runner_stub.write_text("#!/usr/bin/env bash\nprintf 'runner-ran\\n'\n", encoding="utf-8")
    runner_stub.chmod(0o755)

    shell_script = f"""
mkdir -p {shlex.quote(str(lock_dir))}
printf 'not-a-live-pid\\n' > {shlex.quote(str(lock_dir / "pid"))}
HUSHLINE_REPO_DIR={shlex.quote(str(repo_dir))} \
HUSHLINE_DEPENDABOT_QUEUE_LOCK_DIR={shlex.quote(str(lock_dir))} \
HUSHLINE_DEPENDABOT_RUNNER_SCRIPT={shlex.quote(str(runner_stub))} \
{shlex.quote(str(QUEUE_SCRIPT))}
"""

    result = _run_bash(shell_script)

    assert result.returncode == 0, result.stderr
    assert "Removing stale Dependabot queue lock" in result.stdout
    assert "runner-ran" in result.stdout
    assert not lock_dir.exists()
