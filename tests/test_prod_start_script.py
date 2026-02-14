import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prod_start.sh"


def _write_poetry_stub(stub_path: Path) -> Path:
    stub_path.write_text(
        """#!/bin/sh
{
  echo "CALL"
  printf '%s\n' "$@"
} >> "$POETRY_CALLS_FILE"
""",
        encoding="utf-8",
    )
    stub_path.chmod(0o755)
    return stub_path


def _run_script(tmp_path: Path, extra_env: dict[str, str] | None = None) -> list[list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_file = tmp_path / "poetry_calls.txt"
    _write_poetry_stub(bin_dir / "poetry")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["POETRY_CALLS_FILE"] = str(calls_file)
    if extra_env:
        env.update(extra_env)

    subprocess.run(["bash", str(SCRIPT_PATH)], check=True, env=env, cwd=SCRIPT_PATH.parent.parent)

    lines = calls_file.read_text(encoding="utf-8").splitlines()
    calls: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line == "CALL":
            if current:
                calls.append(current)
                current = []
            continue
        current.append(line)
    if current:
        calls.append(current)
    return calls


def _last_flag_value(args: list[str], flag: str) -> str | None:
    value = None
    for idx, arg in enumerate(args):
        if arg == flag and idx + 1 < len(args):
            value = args[idx + 1]
    return value


def test_prod_start_uses_config_when_present(tmp_path: Path) -> None:
    config = tmp_path / "gunicorn.conf.py"
    config.write_text("bind = '0.0.0.0:9999'\n", encoding="utf-8")

    calls = _run_script(tmp_path, {"GUNICORN_CONFIG_PATH": str(config)})
    gunicorn_call = calls[-1]

    assert gunicorn_call[:2] == ["run", "gunicorn"]
    assert "--config" in gunicorn_call
    assert f"file:{config}" in gunicorn_call
    assert "--bind" not in gunicorn_call
    assert gunicorn_call[-1] == "hushline:create_app()"


def test_prod_start_defaults_when_config_missing(tmp_path: Path) -> None:
    calls = _run_script(tmp_path)
    gunicorn_call = calls[-1]

    assert gunicorn_call[:2] == ["run", "gunicorn"]
    assert _last_flag_value(gunicorn_call, "--workers") == "4"
    assert _last_flag_value(gunicorn_call, "--bind") == "0.0.0.0:8080"
    assert "--capture-output" in gunicorn_call
    assert gunicorn_call[-1] == "hushline:create_app()"


def test_prod_start_allows_extra_args(tmp_path: Path) -> None:
    calls = _run_script(
        tmp_path,
        {"GUNICORN_ARGS": "--bind 0.0.0.0:9090 --workers 2"},
    )
    gunicorn_call = calls[-1]

    assert gunicorn_call[:2] == ["run", "gunicorn"]
    assert _last_flag_value(gunicorn_call, "--workers") == "2"
    assert _last_flag_value(gunicorn_call, "--bind") == "0.0.0.0:9090"
    assert gunicorn_call[-1] == "hushline:create_app()"
