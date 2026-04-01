from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

from hushline.public_record_refresh import (
    LinkValidationFailure,
    OfficialStateDiscoveryResult,
    PublicRecordRefreshResult,
    PublicRecordRow,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _workflow_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _assert_markdown_table_row(text: str, *cells: str) -> None:
    pattern = r"\|\s*" + r"\s*\|\s*".join(re.escape(cell) for cell in cells) + r"\s*\|"
    assert re.search(pattern, text)


def _load_refresh_script_module() -> Any:
    script_path = REPO_ROOT / "scripts" / "refresh_public_record_law_firms.py"
    spec = importlib.util.spec_from_file_location(
        "refresh_public_record_law_firms_script",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_record_row(row_id: str, state: str) -> PublicRecordRow:
    return {
        "id": row_id,
        "slug": f"public-record~{row_id}",
        "name": row_id.replace("-", " ").title(),
        "website": "https://example.test",
        "description": "Seed record for workflow tests.",
        "city": "Test City",
        "state": state,
        "practice_tags": ["Whistleblowing"],
        "source_label": "Official public record",
        "source_url": "https://example.test/source",
    }


def test_public_record_quarterly_refresh_workflow_uses_correction_pr_flow() -> None:
    workflow_text = _workflow_text(".github/workflows/public-record-quarterly-refresh.yml")

    assert "workflow_dispatch:" in workflow_text
    assert '- cron: "0 14 1 1,4,7,10 *"' in workflow_text
    assert "REFRESH_REPORT_DIR: .github/tmp/public-record-refresh" in workflow_text
    assert 'mkdir -p "$REFRESH_REPORT_DIR"' in workflow_text
    assert "make refresh-public-record-corrections \\" in workflow_text
    assert (
        'REFRESH_PUBLIC_RECORD_CORRECTION_SUMMARY_OUTPUT="$REFRESH_REPORT_DIR/pr-refresh.md"'
        in workflow_text
    )
    assert (
        'REFRESH_PUBLIC_RECORD_CORRECTION_REPORT_JSON_OUTPUT="$REFRESH_REPORT_DIR/pr-refresh.json"'
        in workflow_text
    )
    assert "actions/upload-artifact@" in workflow_text
    assert ".github/tmp/public-record-refresh/pr-refresh.md" in workflow_text
    assert 'if [ -f "$REFRESH_REPORT_DIR/pr-refresh.md" ];' in workflow_text
    assert "peter-evans/create-pull-request@" in workflow_text
    assert "docs/PUBLIC-RECORD-PROVENANCE-ROADMAP.md" in workflow_text


def test_refresh_public_record_corrections_make_target_matches_workflow_semantics() -> None:
    make_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target_section = make_text.split(".PHONY: refresh-public-record-corrections", 1)[1].split(
        ".PHONY:",
        1,
    )[0]

    assert '--summary-output "$(REFRESH_PUBLIC_RECORD_CORRECTION_SUMMARY_OUTPUT)"' in target_section
    assert (
        '--report-json-output "$(REFRESH_PUBLIC_RECORD_CORRECTION_REPORT_JSON_OUTPUT)"'
        in target_section
    )
    assert "--drop-failing-records" in target_section
    assert "--allow-link-failures" in target_section


def test_refresh_report_matches_structured_values() -> None:
    refresh_script = _load_refresh_script_module()
    refresh_result = PublicRecordRefreshResult(
        rows=[
            _public_record_row("seed-stable", "CA"),
            _public_record_row("seed-new", "WA"),
        ],
        region_counts={"US": 2, "EU": 0},
        checked_url_count=4,
        link_failures=[
            LinkValidationFailure(
                listing_id="seed-broken",
                listing_name="Broken Listing",
                field="source_url",
                url="https://example.test/broken",
                reason="HTTP 404",
            )
        ],
        dropped_record_ids=["seed-broken"],
    )
    report = refresh_script._build_refresh_report(
        baseline_rows=[{"id": "seed-old"}, {"id": "seed-stable"}],
        refresh_result=refresh_result,
        selected_regions=["US", "EU"],
        official_discovery_result=OfficialStateDiscoveryResult(
            rows=[_public_record_row("seed-new", "WA")],
            added_count_by_state={"WA": 1},
            unsupported_states=(),
        ),
    )
    markdown = refresh_script._render_refresh_report_markdown(report)

    assert report["total_strict_listings"] == 2
    assert report["states_covered"] == ["CA", "WA"]
    assert report["rows_added"] == 1
    assert report["rows_removed"] == 1
    assert report["added_ids"] == ["seed-new"]
    assert report["removed_ids"] == ["seed-old"]
    assert report["per_state_counts"]["CA"] == 1
    assert report["per_state_counts"]["WA"] == 1
    assert report["validation_summary"]["link_failures_detected"] == 1
    assert report["validation_summary"]["records_dropped"] == 1
    assert report["official_discovery"]["added_by_state"] == {"WA": 1}

    assert "## Public Record Refresh Report" in markdown
    assert "- Total strict U.S. listings: 2" in markdown
    assert "- Missing states:" in markdown
    assert "### Per-State Counts" in markdown
    assert "| CA | 1 |" in markdown
    assert "| WA | 1 |" in markdown
    assert "### Dataset Drift" in markdown
    assert "  - `seed-new`" in markdown
    assert "  - `seed-old`" in markdown
    assert "### Validation Summary" in markdown
    assert "  - `seed-broken` `source_url` (HTTP 404): https://example.test/broken" in markdown
    assert "### Official Discovery" in markdown
    assert "  - WA: 1" in markdown


def test_sync_provenance_roadmap_updates_baseline_and_adapter_count(tmp_path: Path) -> None:
    refresh_script = _load_refresh_script_module()
    roadmap_path = tmp_path / "PUBLIC-RECORD-PROVENANCE-ROADMAP.md"
    roadmap_path.write_text(
        "\n".join(
            [
                "# Public Record Provenance Roadmap (U.S.)",
                "",
                "## Current Baseline (March 10, 2026)",
                "- Active strict listings: `58`",
                "- States with strict listings: `AK`",
                "",
                "## State Adapter Strategy",
                "",
                "- All 50 states now have explicit adapter entries in discovery code.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    refresh_script._sync_provenance_roadmap(
        roadmap_path,
        report={"total_strict_listings": 2, "states_covered": ["CA", "WA"]},
        generated_on="2026-03-11",
    )

    updated = roadmap_path.read_text(encoding="utf-8")
    assert "## Current Baseline (2026-03-11)" in updated
    assert "- Active strict listings: `2`" in updated
    assert "- States with strict listings: `CA`, `WA`" in updated
    assert "- Explicit state adapter entries in discovery code: 50 / 50." in updated


def test_sync_provenance_roadmap_preserves_eu_planning_section(tmp_path: Path) -> None:
    refresh_script = _load_refresh_script_module()
    roadmap_path = tmp_path / "PUBLIC-RECORD-PROVENANCE-ROADMAP.md"
    roadmap_path.write_text(
        "\n".join(
            [
                "# Public Record Provenance Roadmap (U.S.)",
                "",
                "## Current Baseline (March 10, 2026)",
                "- Active strict listings: `58`",
                "- States with strict listings: `AK`",
                "",
                "## State Adapter Strategy",
                "",
                "- All 50 states now have explicit adapter entries in discovery code.",
                "",
                "## EU Phase 0A (Policy-Only Scaffold)",
                "",
                "| Country | Status |",
                "| ------- | ------ |",
                "| Austria | Candidate |",
                "",
                "### EU Phase 0B (Strict Provenance Gate)",
                "",
                "- `source_url` must be the exact official record URL for that listing.",
                "",
                "### EU Phase 0C (Per-Country Feasibility Survey)",
                "",
                "| Country | Recommendation |",
                "| ------- | -------------- |",
                "| Austria | Open country issue |",
                "",
                "### EU Phase 0D (Shared Normalization and Model Assessment)",
                "",
                "- Country and subdivision data are not preserved by the refresh writer.",
                "",
                "### EU Phase 0E (Rollout Waves and Country-Level Backlog)",
                "",
                "- `Wave 1A` (`Implement first`): `Netherlands`, `Portugal`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    refresh_script._sync_provenance_roadmap(
        roadmap_path,
        report={"total_strict_listings": 2, "states_covered": ["CA", "WA"]},
        generated_on="2026-03-11",
    )

    updated = roadmap_path.read_text(encoding="utf-8")
    assert "## Current Baseline (2026-03-11)" in updated
    assert "## EU Phase 0A (Policy-Only Scaffold)" in updated
    assert "| Austria | Candidate |" in updated
    assert "### EU Phase 0B (Strict Provenance Gate)" in updated
    assert "- `source_url` must be the exact official record URL for that listing." in updated
    assert "### EU Phase 0C (Per-Country Feasibility Survey)" in updated
    assert "| Austria | Open country issue |" in updated
    assert "### EU Phase 0D (Shared Normalization and Model Assessment)" in updated
    assert "- Country and subdivision data are not preserved by the refresh writer." in updated
    assert "### EU Phase 0E (Rollout Waves and Country-Level Backlog)" in updated
    assert "- `Wave 1A` (`Implement first`): `Netherlands`, `Portugal`." in updated


def test_public_record_provenance_roadmap_documents_eu_phase_0b_policy() -> None:
    roadmap_text = _workflow_text("docs/PUBLIC-RECORD-PROVENANCE-ROADMAP.md")

    assert "### EU Phase 0B (Strict Provenance Gate)" in roadmap_text
    assert "- `source_url` must be the exact official record URL for that listing." in roadmap_text
    assert (
        '- The "Expected Official Domain(s)" column in the Phase 0A matrix is planning '
        "evidence only."
    ) in roadmap_text
    assert "| `{Authority Name} attorney directory`" in roadmap_text
    assert "| `{Authority Name} attorney register`" in roadmap_text
    assert "| `{Authority Name} attorney census record`" in roadmap_text
    assert "| `{Authority Name} attorney discipline record`" in roadmap_text
    assert (
        "- Private rankings and editorial products such as Chambers, Legal 500, and "
        "Best Lawyers."
    ) in roadmap_text
    assert "- Lead-generation, referral, or commercial directory sites." in roadmap_text
    assert "- Each exception requires:" in roadmap_text
    assert "  - at least one example record-specific URL per domain" in roadmap_text


def test_public_record_provenance_roadmap_documents_eu_phase_0c_feasibility() -> None:
    roadmap_text = _workflow_text("docs/PUBLIC-RECORD-PROVENANCE-ROADMAP.md")

    assert "### EU Phase 0C (Per-Country Feasibility Survey)" in roadmap_text
    assert (
        "- `Open country issue` means an official attorney-level source exposed a reproducible "
        "record URL shape that appears compatible with Phase 0B strict provenance."
    ) in roadmap_text
    assert "| Austria     |" in roadmap_text
    assert "| Netherlands |" in roadmap_text
    assert "| Portugal    |" in roadmap_text
    assert "| Germany     |" in roadmap_text
    assert "| Italy       |" in roadmap_text
    assert "| Belgium     |" in roadmap_text
    assert "Search-form workflow -> HTML detail-page extraction" in roadmap_text
    assert "HTML detail-page extraction" in roadmap_text
    assert "Search-form workflow -> direct profile extraction" in roadmap_text
    assert "| Open country issue |" in roadmap_text
    assert (
        "- `Defer` means the official source is known, but the current public surface still "
        "lacks a pinned exact-record URL policy, has material workflow instability, or "
        "requires a federated exception that is not yet documented."
    ) in roadmap_text
    assert "expired-dialog or unknown-error state" in roadmap_text
    assert "returned HTTP `403`" in roadmap_text


def test_public_record_provenance_roadmap_documents_eu_phase_0d_shared_requirements() -> None:
    roadmap_text = _workflow_text("docs/PUBLIC-RECORD-PROVENANCE-ROADMAP.md")

    assert "### EU Phase 0D (Shared Normalization and Model Assessment)" in roadmap_text
    assert (
        "- The current automated refresh pipeline still treats `state` as the region key "
        "for public-record rows"
    ) in roadmap_text
    assert (
        "- Country and subdivision data are not preserved by the refresh writer."
    ) in roadmap_text
    assert "- Shared regulator regions are not modeled." in roadmap_text
    assert "- No CSP change is required for Phase 0 planning." in roadmap_text
    assert (
        "- The current refresh pipeline expects deterministic, link-validatable record URLs "
        "and exact allowed domains."
    ) in roadmap_text
    assert "1. Shared EU geography model issue:" in roadmap_text
    assert "2. Shared EU authority metadata issue:" in roadmap_text
    assert "3. Shared EU name-normalization issue:" in roadmap_text


def test_public_record_provenance_roadmap_documents_eu_phase_0e_rollout_backlog() -> None:
    roadmap_text = _workflow_text("docs/PUBLIC-RECORD-PROVENANCE-ROADMAP.md")

    assert "### EU Phase 0E (Rollout Waves and Country-Level Backlog)" in roadmap_text
    assert (
        "- Move a country from research into implementation only when a country issue " "records:"
    ) in roadmap_text
    assert (
        "- Keep a country out of implementation when any of the following remain true:"
    ) in roadmap_text
    assert "1. `Wave 1A` (`Implement first`): `Netherlands`, `Portugal`." in roadmap_text
    assert "2. `Wave 1B` (`Implement first`): `Austria`." in roadmap_text
    assert (
        "3. `Wave 2` (`Implement later`): `Finland`, `France`, `Luxembourg`, " "`Spain`, `Sweden`."
    ) in roadmap_text
    assert "4. `Deferred backlog` (`Defer`): `Belgium`, `Germany`, `Italy`." in roadmap_text
    _assert_markdown_table_row(roadmap_text, "Austria", "Implement first", "Wave 1B")
    _assert_markdown_table_row(roadmap_text, "Netherlands", "Implement first", "Wave 1A")
    _assert_markdown_table_row(roadmap_text, "Portugal", "Implement first", "Wave 1A")
    _assert_markdown_table_row(roadmap_text, "Finland", "Implement later", "Wave 2")
    _assert_markdown_table_row(roadmap_text, "France", "Implement later", "Wave 2")
    _assert_markdown_table_row(roadmap_text, "Sweden", "Implement later", "Wave 2")
    _assert_markdown_table_row(roadmap_text, "Belgium", "Defer", "Deferred backlog")
    _assert_markdown_table_row(roadmap_text, "Germany", "Defer", "Deferred backlog")
    _assert_markdown_table_row(roadmap_text, "Italy", "Defer", "Deferred backlog")
    _assert_markdown_table_row(
        roadmap_text,
        "`EU Wave 1A: implement Netherlands and Portugal attorney adapters`",
        "Netherlands, Portugal",
        "Implementation",
    )
    _assert_markdown_table_row(
        roadmap_text,
        "`EU Wave 2A: validate Finland, Luxembourg, and Sweden official attorney detail URLs`",
        "Finland, Luxembourg, Sweden",
        "Research -> implementation backlog",
    )
    _assert_markdown_table_row(
        roadmap_text,
        "`EU defer backlog: Germany official register stability and provenance validation`",
        "Germany",
        "Deferred backlog",
    )
    assert "expired-dialog or unknown-error state on March 14, 2026" in roadmap_text
    assert "returned HTTP `403` on March 14, 2026" in roadmap_text
