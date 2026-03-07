#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, TypedDict, cast


class PublicDirectorySnapshotError(Exception):
    """Raised when the directory snapshot input is invalid."""


class DiffSummary(TypedDict):
    baseline_count: int
    new_count: int
    removed_count: int
    new_usernames: list[str]
    removed_usernames: list[str]
    has_baseline: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare public Hush Line directory user snapshots and "
            "report weekly additions/removals."
        ),
    )
    parser.add_argument(
        "--current", type=Path, required=True, help="Current directory JSON snapshot."
    )
    parser.add_argument(
        "--previous-sync",
        type=Path,
        default=None,
        help="Optional previous normalized snapshot JSON for the last-sync comparison.",
    )
    parser.add_argument(
        "--previous-week",
        type=Path,
        default=None,
        help="Optional normalized snapshot JSON for the last-week comparison.",
    )
    parser.add_argument(
        "--snapshot-history-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory of timestamped snapshot JSON files used to resolve "
            "last-sync and last-week comparisons automatically."
        ),
    )
    parser.add_argument(
        "--snapshot-output",
        type=Path,
        default=None,
        help="Optional output path for the normalized current snapshot JSON.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Optional Markdown report output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON summary output path.",
    )
    return parser.parse_args()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublicDirectorySnapshotError(f"Input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PublicDirectorySnapshotError(f"Input file is not valid JSON: {path}") from exc

    if not isinstance(parsed, list):
        raise PublicDirectorySnapshotError(f"Input root must be a JSON array: {path}")
    if not all(isinstance(row, dict) for row in parsed):
        raise PublicDirectorySnapshotError(f"Input array must contain only JSON objects: {path}")
    if not all(all(isinstance(key, str) for key in row) for row in parsed):
        raise PublicDirectorySnapshotError(f"Input rows must use string keys only: {path}")

    return [dict(row) for row in parsed]


def _is_public_user_row(row: Mapping[str, object]) -> bool:
    primary_username = row.get("primary_username")
    if not isinstance(primary_username, str) or not primary_username.strip():
        return False

    entry_type = row.get("entry_type")
    if isinstance(entry_type, str) and entry_type.strip():
        return entry_type == "user"

    return not bool(row.get("is_public_record")) and not bool(row.get("is_securedrop"))


def build_snapshot(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    users_by_username: dict[str, dict[str, object]] = {}
    for row in rows:
        if not _is_public_user_row(row):
            continue

        username = str(row["primary_username"]).strip()
        display_name = row.get("display_name")
        profile_url = row.get("profile_url")
        users_by_username[username] = {
            "primary_username": username,
            "display_name": display_name
            if isinstance(display_name, str) and display_name
            else username,
            "profile_url": profile_url if isinstance(profile_url, str) else "",
            "is_verified": bool(row.get("is_verified")),
            "has_pgp_key": bool(row.get("has_pgp_key")),
        }

    return [users_by_username[key] for key in sorted(users_by_username)]


def _snapshot_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["primary_username"]): row for row in rows}


def _build_diff_summary(
    current_snapshot: list[dict[str, object]],
    baseline_snapshot: list[dict[str, object]],
) -> DiffSummary:
    current_map = _snapshot_map(current_snapshot)
    baseline_map = _snapshot_map(baseline_snapshot)

    current_usernames = set(current_map)
    baseline_usernames = set(baseline_map)

    added_usernames = sorted(current_usernames - baseline_usernames)
    removed_usernames = sorted(baseline_usernames - current_usernames)

    return {
        "baseline_count": len(baseline_snapshot),
        "new_count": len(added_usernames),
        "removed_count": len(removed_usernames),
        "new_usernames": added_usernames,
        "removed_usernames": removed_usernames,
        "has_baseline": True,
    }


def _resolve_history_baselines(
    snapshot_history_dir: Path,
    *,
    now: datetime | None = None,
) -> tuple[Path | None, Path | None]:
    paths: list[tuple[datetime, Path]] = []
    for path in sorted(snapshot_history_dir.glob("*.json")):
        try:
            timestamp = datetime.strptime(path.stem, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        paths.append((timestamp, path))

    if not paths:
        return None, None

    current_time = now or datetime.now(UTC)
    cutoff = current_time - timedelta(days=7)
    last_sync = paths[-1][1]
    last_week_candidates = [path for timestamp, path in paths if timestamp <= cutoff]
    last_week = last_week_candidates[-1] if last_week_candidates else None
    return last_sync, last_week


def _append_diff_section(
    lines: list[str],
    title: str,
    current_snapshot: list[dict[str, object]],
    baseline_snapshot: list[dict[str, object]] | None,
) -> DiffSummary:
    lines.extend(["", f"### {title}", ""])

    if baseline_snapshot is None:
        lines.append("- No comparison snapshot available yet.")
        return {
            "baseline_count": 0,
            "new_count": 0,
            "removed_count": 0,
            "new_usernames": [],
            "removed_usernames": [],
            "has_baseline": False,
        }

    current_map = _snapshot_map(current_snapshot)
    baseline_map = _snapshot_map(baseline_snapshot)
    diff = _build_diff_summary(current_snapshot, baseline_snapshot)

    lines.extend(
        [
            f"- Baseline listings: {diff['baseline_count']}",
            f"- New public listings: {diff['new_count']}",
            f"- Removed public listings: {diff['removed_count']}",
            "",
            "#### New Public Listings",
            "",
        ]
    )

    if diff["new_usernames"]:
        for username in cast(list[str], diff["new_usernames"]):
            row = current_map[str(username)]
            lines.append(
                f"- `{username}`"
                f" ({row['display_name']})"
                f" - {row['profile_url'] or 'profile URL unavailable'}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "#### Removed Public Listings", ""])
    if diff["removed_usernames"]:
        for username in cast(list[str], diff["removed_usernames"]):
            row = baseline_map[str(username)]
            lines.append(
                f"- `{username}`"
                f" ({row['display_name']})"
                f" - {row['profile_url'] or 'profile URL unavailable'}"
            )
    else:
        lines.append("- none")
    return diff


def build_markdown_report(
    current_snapshot: list[dict[str, object]],
    previous_sync_snapshot: list[dict[str, object]] | None,
    previous_week_snapshot: list[dict[str, object]] | None,
) -> tuple[str, dict[str, object]]:
    lines: list[str] = [
        "## Public Directory Snapshot Report",
        "",
        f"- Current public listings: {len(current_snapshot)}",
    ]

    last_sync_summary = _append_diff_section(
        lines,
        "Changes Since Last Sync",
        current_snapshot,
        previous_sync_snapshot,
    )
    last_week_summary = _append_diff_section(
        lines,
        "Changes Since Last Week",
        current_snapshot,
        previous_week_snapshot,
    )

    summary: dict[str, object] = {
        "current_count": len(current_snapshot),
        "last_sync": last_sync_summary,
        "last_week": last_week_summary,
    }
    return ("\n".join(lines) + "\n", summary)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def main() -> int:
    args = _parse_args()
    current_rows = _load_rows(args.current)
    previous_sync_path = args.previous_sync
    previous_week_path = args.previous_week
    if args.snapshot_history_dir is not None:
        history_sync_path, history_week_path = _resolve_history_baselines(args.snapshot_history_dir)
        if previous_sync_path is None:
            previous_sync_path = history_sync_path
        if previous_week_path is None:
            previous_week_path = history_week_path
    previous_sync_rows = (
        _load_rows(previous_sync_path)
        if previous_sync_path is not None and previous_sync_path.exists()
        else None
    )
    previous_week_rows = (
        _load_rows(previous_week_path)
        if previous_week_path is not None and previous_week_path.exists()
        else None
    )

    current_snapshot = build_snapshot(current_rows)
    previous_sync_snapshot = (
        build_snapshot(previous_sync_rows) if previous_sync_rows is not None else None
    )
    previous_week_snapshot = (
        build_snapshot(previous_week_rows) if previous_week_rows is not None else None
    )
    report, summary = build_markdown_report(
        current_snapshot,
        previous_sync_snapshot,
        previous_week_snapshot,
    )

    print(report, end="")

    if args.snapshot_output is not None:
        _write_json(args.snapshot_output, current_snapshot)
    if args.report_output is not None:
        _write_text(args.report_output, report)
    if args.json_output is not None:
        _write_json(args.json_output, summary)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicDirectorySnapshotError as exc:
        print(f"public_directory_snapshot_report.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
