from __future__ import annotations

from pathlib import Path


def test_audit_issue_template_includes_required_tracks_and_sections() -> None:
    template_path = (
        Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE" / "audit_report.yml"
    )
    assert template_path.exists()

    template = template_path.read_text(encoding="utf-8")

    assert "name: Audit Report" in template
    assert 'title: "[Audit][Track] "' in template

    for track in (
        "Usability",
        "Security",
        "Accessibility",
        "Writing/Docs",
        "Performance",
        "Code Quality",
    ):
        assert f"- {track}" in template

    for section in (
        "1) Scope",
        "2) Method",
        "3) Findings",
        "4) Recommendations",
        "5) Optional contribution",
    ):
        assert f"label: {section}" in template
