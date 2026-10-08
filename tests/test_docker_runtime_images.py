import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RUNTIME_IMAGE = "FROM python:3.13-slim-bookworm"


def _python_runtime_base(relative_path: str) -> str:
    dockerfile = (ROOT / relative_path).read_text(encoding="utf-8")

    for line in dockerfile.splitlines():
        if line.startswith("FROM python:"):
            return line

    raise AssertionError(f"No Python runtime base image found in {relative_path}")


def test_dev_and_prod_dockerfiles_use_the_same_python_313_bookworm_runtime_image() -> None:
    assert _python_runtime_base("Dockerfile.dev") == EXPECTED_RUNTIME_IMAGE
    assert _python_runtime_base("Dockerfile.prod") == EXPECTED_RUNTIME_IMAGE


@pytest.mark.local_only()
def test_customer_driver_accepts_workflow_paths_as_arguments() -> None:
    if os.environ.get("SINGLE_TENANT_DRIVER_CONTAINER_SMOKE") != "1":
        pytest.skip("Build the customer driver smoke image before enabling this test")
    result = subprocess.run(
        [  # noqa: S603,S607 — fixed local image and arguments; no cloud credentials
            "docker",
            "run",
            "--rm",
            "hushline-single-tenant-driver-smoke",
            "/infra/hushline-single-tenant",
            "/results",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "single_tenant_live_run.py" in result.stdout
    assert "root" in result.stdout
    assert "result" in result.stdout
