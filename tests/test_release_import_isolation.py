"""Exercise the privileged interpreter command with harmless shadow-module canaries."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_secret_bearing_release_python_ignores_repository_and_pythonpath(
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitignore").write_text("*\n")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("deploy_published_release.py", "single_tenant_live_image.py"):
        shutil.copyfile(REPO / "scripts" / name, scripts / name)
    marker = tmp_path / "shadow-executed"
    payload = (
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('shadow')\n"
    )
    for directory in (scripts, tmp_path):
        for name in ("json.py", "runpy.py", "sitecustomize.py"):
            (directory / name).write_text(payload)
    (scripts / "__init__.py").write_text(payload)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"workflow_run": {"conclusion": "failure"}}))
    result = subprocess.run(
        [sys.executable, "-I", str(scripts / "deploy_published_release.py")],  # noqa: S603 - Fixed Python executable, isolation flag and test fixture path.
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(tmp_path),
            "GITHUB_EVENT_NAME": "workflow_run",
            "GITHUB_EVENT_PATH": str(event),
            "RELEASE_GITHUB_TOKEN": "synthetic-test-token",
            "RELEASE_TF_TOKEN": "synthetic-test-token",
            "RELEASE_SIGNING_KEY": "synthetic-test-key",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()


def test_workflow_uses_isolation_for_every_secret_bearing_python_command() -> None:
    text = (REPO / ".github/workflows/deploy-published-release.yml").read_text()
    commands = [line.strip() for line in text.splitlines() if line.strip().startswith("python3 ")]
    assert commands == ["python3 -I - <<'PY'", "python3 -I scripts/deploy_published_release.py"]


def test_governance_covers_shadow_modules_and_explicit_image_helper() -> None:
    text = (REPO / ".github/workflows/release-governance.yml").read_text()
    pattern = re.search(r"governed_path_pattern='([^']+)'", text)
    assert pattern is not None
    for path in (
        "scripts/json.py",
        "scripts/__init__.py",
        "scripts/single_tenant_live_image.py",
        "scripts/nested/json.py",
    ):
        assert re.fullmatch(pattern[1], path) is not None
