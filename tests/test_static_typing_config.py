from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_mypy_targets_python_313_semantics() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["mypy"]["python_version"] == "3.13"
