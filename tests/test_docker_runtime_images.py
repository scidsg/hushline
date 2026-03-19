from pathlib import Path

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
