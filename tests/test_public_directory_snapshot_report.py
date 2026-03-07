from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "public_directory_snapshot_report.py"
    )
    spec = importlib.util.spec_from_file_location("public_directory_snapshot_report", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_snapshot_filters_to_public_hushline_users() -> None:
    module = _load_module()

    rows = [
        {
            "entry_type": "user",
            "primary_username": "artvandelay",
            "display_name": "Art Vandelay",
            "profile_url": "/to/artvandelay",
            "is_verified": True,
            "has_pgp_key": True,
        },
        {
            "entry_type": "public_record",
            "primary_username": None,
            "display_name": "Example Law Office",
            "profile_url": "/directory/public-records/example-law-office",
            "is_public_record": True,
        },
        {
            "entry_type": "securedrop",
            "primary_username": None,
            "display_name": "Example SecureDrop",
            "profile_url": "/directory/securedrop/example",
            "is_securedrop": True,
        },
        {
            "primary_username": "infoonly",
            "display_name": "Info Only",
            "profile_url": "/to/infoonly",
            "is_public_record": False,
            "is_securedrop": False,
            "has_pgp_key": False,
        },
    ]

    assert module.build_snapshot(rows) == [
        {
            "primary_username": "artvandelay",
            "display_name": "Art Vandelay",
            "profile_url": "/to/artvandelay",
            "is_verified": True,
            "has_pgp_key": True,
        },
        {
            "primary_username": "infoonly",
            "display_name": "Info Only",
            "profile_url": "/to/infoonly",
            "is_verified": False,
            "has_pgp_key": False,
        },
    ]


def test_build_markdown_report_reports_added_and_removed_usernames() -> None:
    module = _load_module()

    previous_sync_snapshot = [
        {
            "primary_username": "olduser",
            "display_name": "Old User",
            "profile_url": "/to/olduser",
            "is_verified": False,
            "has_pgp_key": True,
        },
        {
            "primary_username": "stableuser",
            "display_name": "Stable User",
            "profile_url": "/to/stableuser",
            "is_verified": True,
            "has_pgp_key": True,
        },
    ]
    previous_week_snapshot = [
        {
            "primary_username": "olduser",
            "display_name": "Old User",
            "profile_url": "/to/olduser",
            "is_verified": False,
            "has_pgp_key": True,
        },
        {
            "primary_username": "weekolduser",
            "display_name": "Week Old User",
            "profile_url": "/to/weekolduser",
            "is_verified": True,
            "has_pgp_key": True,
        },
        {
            "primary_username": "stableuser",
            "display_name": "Stable User",
            "profile_url": "/to/stableuser",
            "is_verified": True,
            "has_pgp_key": True,
        },
    ]
    current_snapshot = [
        {
            "primary_username": "newuser",
            "display_name": "New User",
            "profile_url": "/to/newuser",
            "is_verified": False,
            "has_pgp_key": True,
        },
        {
            "primary_username": "stableuser",
            "display_name": "Stable User",
            "profile_url": "/to/stableuser",
            "is_verified": True,
            "has_pgp_key": True,
        },
    ]

    report, summary = module.build_markdown_report(
        current_snapshot,
        previous_sync_snapshot,
        previous_week_snapshot,
    )

    assert "### Changes Since Last Sync" in report
    assert "### Changes Since Last Week" in report
    assert report.count("- New public listings: 1") == 2
    assert "- Removed public listings: 2" in report
    assert "`newuser` (New User) - /to/newuser" in report
    assert "`olduser` (Old User) - /to/olduser" in report
    assert "`weekolduser` (Week Old User) - /to/weekolduser" in report
    assert summary == {
        "current_count": 2,
        "last_sync": {
            "baseline_count": 2,
            "new_count": 1,
            "removed_count": 1,
            "new_usernames": ["newuser"],
            "removed_usernames": ["olduser"],
            "has_baseline": True,
        },
        "last_week": {
            "baseline_count": 3,
            "new_count": 1,
            "removed_count": 2,
            "new_usernames": ["newuser"],
            "removed_usernames": ["olduser", "weekolduser"],
            "has_baseline": True,
        },
    }


def test_resolve_history_baselines_uses_latest_sync_and_week_old_snapshot(tmp_path: Path) -> None:
    module = _load_module()

    history_dir = tmp_path / "snapshots"
    history_dir.mkdir()
    latest = history_dir / "2026-03-07T12-00-00Z.json"
    midweek = history_dir / "2026-03-05T12-00-00Z.json"
    week_old = history_dir / "2026-02-27T12-00-00Z.json"
    ignored = history_dir / "latest.json"
    for path in (latest, midweek, week_old, ignored):
        path.write_text("[]\n", encoding="utf-8")

    last_sync, last_week = module._resolve_history_baselines(
        history_dir,
        now=module.datetime(2026, 3, 7, 18, 0, 0, tzinfo=module.UTC),
    )

    assert last_sync == latest
    assert last_week == week_old
