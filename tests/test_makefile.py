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
    assert "prettier $(PRETTIER_FLAGS) --write" in target_section
    assert "$(MAKE) lint" in target_section


def test_lint_target_keeps_format_check_before_ruff_check() -> None:
    target_section = _target_section("lint")

    assert "$(CMD) poetry run ruff format --check && \\" in target_section
    assert "$(CMD) poetry run ruff check --output-format full && \\" in target_section
    assert target_section.index("ruff format --check") < target_section.index(
        "ruff check --output-format full"
    )


def test_prettier_targets_skip_generated_static_js_glob() -> None:
    make_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "./hushline/static/js/*.js" not in make_text
    assert "./hushline/static/js/directory_verified.js" in make_text
    assert "./hushline/static/js/settings-location.js" in make_text


def test_test_target_writes_html_coverage_to_tmp_by_default() -> None:
    target_section = _target_section("test")

    assert "COVERAGE_HTML_DIR ?= /tmp/hushline-htmlcov" in (REPO_ROOT / "Makefile").read_text(
        encoding="utf-8"
    )
    assert "--cov-report term-missing" in target_section
    assert "--cov-report html:$(COVERAGE_HTML_DIR)" in target_section


def test_release_target_invokes_release_helper_with_prod_defaults() -> None:
    make_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target_section = _target_section("release")

    assert "RELEASE_PROD_URL ?= https://tips.hushline.app/" in make_text
    assert "RELEASE_BRANCH ?= main" in make_text
    assert "RELEASE_ALLOWED_SIGNERS ?= .github/release-allowed-signers" in make_text
    assert (
        "RELEASE_SIGNING_KEY ?= $(HOME)/.ssh/hushline-release/primary-release-yubikey"
        in make_text
    )
    assert "RELEASE_DRY_RUN ?=" in make_text
    assert "release: ## Bump patch version, tag, and publish a GitHub release" in target_section
    assert 'HUSHLINE_RELEASE_PROD_URL="$(RELEASE_PROD_URL)"' in target_section
    assert 'HUSHLINE_RELEASE_BRANCH="$(RELEASE_BRANCH)"' in target_section
    assert 'HUSHLINE_RELEASE_ALLOWED_SIGNERS="$(RELEASE_ALLOWED_SIGNERS)"' in target_section
    assert 'HUSHLINE_RELEASE_SIGNING_KEY="$(RELEASE_SIGNING_KEY)"' in target_section
    assert 'HUSHLINE_RELEASE_DRY_RUN="$(RELEASE_DRY_RUN)"' in target_section
    assert "python3 scripts/release.py" in target_section


def test_release_dry_run_target_invokes_release_with_dry_run_enabled() -> None:
    target_section = _target_section("release-dry-run")

    assert (
        "release-dry-run: ## Check release preflight and YubiKey authorization without publishing"
        in target_section
    )
    assert "$(MAKE) release RELEASE_DRY_RUN=1" in target_section
