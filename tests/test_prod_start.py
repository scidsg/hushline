import os
import subprocess


def _run_prod_start(tmp_path, run_migrations: bool) -> list[str]:
    log_path = tmp_path / "poetry.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    poetry_path = bin_dir / "poetry"

    poetry_path.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> \"{log_path}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    poetry_path.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH','')}"
    env["RUN_STARTUP_MIGRATIONS"] = "true" if run_migrations else "false"
    env.pop("STRIPE_SECRET_KEY", None)

    subprocess.run(
        ["bash", "scripts/prod_start.sh"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    if not log_path.exists():
        return []
    return log_path.read_text(encoding="utf-8").splitlines()


def test_prod_start_skips_migrations_when_disabled(tmp_path) -> None:
    lines = _run_prod_start(tmp_path, run_migrations=False)

    assert any("gunicorn" in line for line in lines)
    assert not any("flask db upgrade" in line for line in lines)


def test_prod_start_runs_migrations_when_enabled(tmp_path) -> None:
    lines = _run_prod_start(tmp_path, run_migrations=True)

    assert any("gunicorn" in line for line in lines)
    assert any("flask db upgrade" in line for line in lines)
