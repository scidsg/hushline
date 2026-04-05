from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _target_section(target_name: str) -> str:
    make_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    return make_text.split(f".PHONY: {target_name}", 1)[1].split(".PHONY:", 1)[0]


def test_fix_target_runs_ruff_fix_before_formatting() -> None:
    target_section = _target_section("fix")

    assert "fix: ## Auto-fix supported lint and format issues" in target_section
    assert "poetry run ruff check --fix || true;" in target_section
    assert "poetry run ruff format;" in target_section
    assert target_section.index("ruff check --fix") < target_section.index("ruff format")
    assert "prettier --write" in target_section
    assert "$(MAKE) lint" in target_section


def test_lint_target_keeps_format_check_before_ruff_check() -> None:
    target_section = _target_section("lint")

    assert "$(CMD) poetry run ruff format --check && \\" in target_section
    assert "$(CMD) poetry run ruff check --output-format full && \\" in target_section
    assert target_section.index("ruff format --check") < target_section.index(
        "ruff check --output-format full"
    )
