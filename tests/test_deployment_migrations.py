from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _service_blocks(compose_path: Path) -> dict[str, str]:
    lines = compose_path.read_text(encoding="utf-8").splitlines()
    blocks: dict[str, list[str]] = {}
    in_services = False
    current_service: str | None = None

    for line in lines:
        stripped = line.strip()
        if stripped == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    "):
            service_name, separator, _ = stripped.partition(":")
            if separator == ":" and service_name:
                current_service = service_name
                blocks[current_service] = []
                continue
        if current_service is not None:
            blocks[current_service].append(line)

    return {name: "\n".join(block) for name, block in blocks.items()}


def test_staging_compose_uses_migration_sidecar() -> None:
    blocks = _service_blocks(ROOT / "docker-compose.staging.yaml")

    assert "migrations" in blocks
    migrations = blocks["migrations"]
    assert "<<: *app_env" in migrations
    assert "ports: []" in migrations
    assert "command: poetry run flask db upgrade" in migrations
    assert "restart: on-failure" in migrations
    assert "condition: service_healthy" in migrations


def test_staging_compose_disables_app_startup_migrations() -> None:
    blocks = _service_blocks(ROOT / "docker-compose.staging.yaml")

    app = blocks["app"]
    assert 'RUN_STARTUP_MIGRATIONS: "false"' in app
    assert "migrations:" in app
    assert "condition: service_completed_successfully" in app


def test_prod_start_script_supports_disabling_startup_migrations() -> None:
    script = (ROOT / "scripts/prod_start.sh").read_text(encoding="utf-8")

    assert 'if [ "${RUN_STARTUP_MIGRATIONS:-true}" = "true" ]; then' in script
    assert 'echo "> Skipping startup migrations"' in script
