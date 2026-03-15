import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "screenshots" / "scenes.json"


def _scene_map() -> dict[str, dict[str, object]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {scene["slug"]: scene for scene in manifest["scenes"]}


def test_docs_screenshots_manifest_covers_guest_directory_verified_subtabs() -> None:
    scenes = _scene_map()

    expected_paths = {
        "guest-directory-attorneys-closed-filters": "/directory",
        "guest-directory-attorneys-open-filters": "/directory",
        "guest-directory-attorneys-applied-filters": "/directory?country=US&region=CA",
        "guest-directory-attorney-adam-j-levitt": (
            "/directory/public-records/public-record~adam-j-levitt"
        ),
        "guest-directory-securedrop": "/directory",
        "guest-directory-globaleaks": "/directory",
    }

    for slug, path in expected_paths.items():
        scene = scenes[slug]
        assert scene["session"] == "guest"
        assert scene["path"] == path
        assert "viewports" not in scene
        assert "themes" not in scene

    assert scenes["guest-directory-attorneys-closed-filters"]["actions"] == [
        {"type": "click", "selector": "#public-records-tab"},
        {"type": "wait_for", "selector": "#public-records.tab-content.active"},
        {
            "type": "wait_for",
            "selector": "#attorney-filters-toggle-shell:not([hidden]) #attorney-filters-toggle",
        },
    ]
    assert scenes["guest-directory-attorneys-open-filters"]["actions"] == [
        {"type": "click", "selector": "#public-records-tab"},
        {"type": "wait_for", "selector": "#public-records.tab-content.active"},
        {
            "type": "wait_for",
            "selector": "#attorney-filters-toggle-shell:not([hidden]) #attorney-filters-toggle",
        },
        {"type": "click", "selector": "#attorney-filters-toggle"},
        {"type": "wait_for", "selector": "#attorney-filters-panel:not([hidden])"},
    ]
    assert scenes["guest-directory-attorneys-applied-filters"]["actions"] == [
        {"type": "click", "selector": "#public-records-tab"},
        {"type": "wait_for", "selector": "#public-records.tab-content.active"},
        {"type": "wait_for", "selector": "#attorney-filters-panel:not([hidden])"},
        {
            "type": "wait_for",
            "selector": "#attorney-country-filter option:checked[value='United States']",
        },
        {
            "type": "wait_for",
            "selector": "#attorney-region-filter option:checked[value='CA']",
        },
    ]
    assert scenes["guest-directory-attorney-adam-j-levitt"]["waitForSelector"] == "h2.submit"
    assert scenes["guest-directory-securedrop"]["actions"] == [
        {"type": "click", "selector": "#securedrop-tab"},
        {"type": "wait_for", "selector": "#securedrop.tab-content.active"},
    ]
    assert scenes["guest-directory-globaleaks"]["actions"] == [
        {"type": "click", "selector": "#globaleaks-tab"},
        {"type": "wait_for", "selector": "#globaleaks.tab-content.active"},
    ]
