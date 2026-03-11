from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _workflow_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


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


def test_public_record_quarterly_refresh_workflow_uses_correction_pr_flow() -> None:
    workflow_text = _workflow_text(".github/workflows/public-record-quarterly-refresh.yml")

    assert "workflow_dispatch:" in workflow_text
    assert '- cron: "0 14 1 1,4,7,10 *"' in workflow_text
    assert "make refresh-public-record-corrections \\" in workflow_text
    assert "REFRESH_PUBLIC_RECORD_CORRECTION_SUMMARY_OUTPUT=/tmp/pr-refresh.md" in workflow_text
    assert "peter-evans/create-pull-request@" in workflow_text


def test_refresh_public_record_corrections_make_target_matches_workflow_semantics() -> None:
    make_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target_section = make_text.split(".PHONY: refresh-public-record-corrections", 1)[1].split(
        ".PHONY:",
        1,
    )[0]

    assert '--summary-output "$(REFRESH_PUBLIC_RECORD_CORRECTION_SUMMARY_OUTPUT)"' in target_section
    assert "--drop-failing-records" in target_section
    assert "--allow-link-failures" in target_section


def test_refresh_summary_reports_dataset_drift_counts_and_ids() -> None:
    refresh_script = _load_refresh_script_module()
    summary = refresh_script._append_dataset_drift_summary(
        "## Public Record Refresh Summary\n",
        baseline_rows=[{"id": "seed-old"}, {"id": "seed-stable"}],
        refreshed_rows=[{"id": "seed-stable"}, {"id": "seed-new"}],
    )

    assert "### Dataset Drift" in summary
    assert "- Rows added: 1" in summary
    assert "- Rows removed: 1" in summary
    assert "- Added IDs:" in summary
    assert "  - `seed-new`" in summary
    assert "- Removed IDs:" in summary
    assert "  - `seed-old`" in summary
