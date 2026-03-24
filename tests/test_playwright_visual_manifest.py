import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "tests" / "playwright" / "visual-scenes.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_playwright_visual_manifest_covers_requested_scenes_in_all_modes() -> None:
    manifest = _manifest()
    scenes = {scene["slug"]: scene for scene in manifest["scenes"]}

    assert [viewport["id"] for viewport in manifest["viewports"]] == ["desktop", "mobile"]
    assert manifest["themes"] == ["light", "dark"]

    expected_scene_slugs = {
        "guest-directory-verified",
        "guest-directory-securedrop",
        "guest-directory-globaleaks",
        "guest-profile-artvandelay",
        "guest-profile-admin",
        "auth-admin-profile",
        "auth-admin-settings",
        "auth-artvandelay-inbox",
        "auth-admin-inbox",
        "auth-artvandelay-inbox-empty",
        "auth-admin-inbox-empty",
        "auth-admin-settings-profile",
        "auth-admin-settings-aliases",
        "auth-admin-settings-auth",
        "auth-admin-settings-branding",
        "auth-admin-settings-encryption",
        "auth-admin-settings-replies",
        "auth-admin-settings-notifications",
        "auth-admin-settings-guidance",
        "auth-admin-settings-registration",
        "auth-admin-settings-advanced",
        "auth-admin-settings-admin",
    }

    assert set(scenes) == expected_scene_slugs
    assert all(scene["fullPage"] is True for scene in scenes.values())


def test_playwright_visual_manifest_uses_visual_only_inbox_states() -> None:
    manifest = _manifest()
    scenes = {scene["slug"]: scene for scene in manifest["scenes"]}

    assert scenes["auth-artvandelay-inbox"]["actions"] == [
        {
            "type": "render_inbox_state",
            "messageCount": 6,
        }
    ]
    assert scenes["auth-admin-inbox"]["actions"] == [
        {
            "type": "render_inbox_state",
            "messageCount": 6,
        }
    ]
    assert scenes["auth-artvandelay-inbox-empty"]["actions"] == [
        {
            "type": "render_inbox_state",
            "messageCount": 0,
        }
    ]
    assert scenes["auth-admin-inbox-empty"]["actions"] == [
        {
            "type": "render_inbox_state",
            "messageCount": 0,
        }
    ]
