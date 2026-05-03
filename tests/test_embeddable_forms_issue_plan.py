from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
PLAN_PATH = DOCS_ROOT / "EMBEDDABLE-E2EE-PROFILE-FORMS-MVP-EPIC.md"
FEASIBILITY_PATH = DOCS_ROOT / "EMBEDDABLE-E2EE-PROFILE-FORMS-FEASIBILITY.md"


def test_embeddable_forms_mvp_plan_tracks_feasibility_study() -> None:
    plan = PLAN_PATH.read_text(encoding="utf-8")
    feasibility = FEASIBILITY_PATH.read_text(encoding="utf-8")

    assert "restricted hosted iframe embed" in feasibility
    assert "Source feasibility study" in plan
    assert "./EMBEDDABLE-E2EE-PROFILE-FORMS-FEASIBILITY.md" in plan
    assert "Hush Line-hosted iframe endpoint" in plan
    assert "Reject script widgets" in plan
    assert "Do not broaden CORS" in plan
    assert "frame-ancestors 'none'" in plan
    assert "X-Frame-Options: DENY" in plan
    assert 'referrerpolicy="no-referrer"' in plan
    assert "postMessage" in plan
    assert "no-JS server-side fallback" in plan


def test_embeddable_forms_mvp_plan_has_epic_and_scoped_child_issues() -> None:
    plan = PLAN_PATH.read_text(encoding="utf-8")

    assert "## Epic: Embeddable Hush Line Profile Forms MVP" in plan

    child_headings = [line for line in plan.splitlines() if line.startswith("## Child Issue ")]

    assert child_headings == [
        "## Child Issue 1: Add Embed Eligibility, Opt-In, and Origin Allowlist Model",
        "## Child Issue 2: Add Admin and Recipient Embed Controls and Generated Iframe Snippets",
        "## Child Issue 3: Add Hush Line-Hosted Embed Form Endpoint With Dedicated Frame Headers",
        (
            "## Child Issue 4: Preserve Secure Embed Submissions With E2EE, CSRF, "
            "CAPTCHA, and Owner Guard"
        ),
        (
            "## Child Issue 5: Harden Embed UX for Trust Chrome, Emergency Exit, "
            "No-JS Fallback, Accessibility, and Mobile"
        ),
        "## Child Issue 6: Add Embed Documentation, Abuse Controls, and Logging Privacy Safeguards",
    ]

    assert plan.count("Parent epic: `#<epic-number>`") == len(child_headings)
