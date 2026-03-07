#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


class PublicDirectorySnapshotError(Exception):
    """Raised when the directory snapshot input is invalid."""


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
        "--previous",
        type=Path,
        default=None,
        help="Optional previous normalized snapshot JSON.",
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


def build_markdown_report(
    current_snapshot: list[dict[str, object]],
    previous_snapshot: list[dict[str, object]],
) -> tuple[str, dict[str, object]]:
    current_map = _snapshot_map(current_snapshot)
    previous_map = _snapshot_map(previous_snapshot)

    current_usernames = set(current_map)
    previous_usernames = set(previous_map)

    added_usernames = sorted(current_usernames - previous_usernames)
    removed_usernames = sorted(previous_usernames - current_usernames)

    lines: list[str] = [
        "## Weekly Public Directory Report",
        "",
        f"- Current public listings: {len(current_snapshot)}",
        f"- Previous snapshot listings: {len(previous_snapshot)}",
        f"- New public listings: {len(added_usernames)}",
        f"- Removed public listings: {len(removed_usernames)}",
        "",
        "### New Public Listings",
        "",
    ]

    if added_usernames:
        for username in added_usernames:
            row = current_map[username]
            lines.append(
                f"- `{username}`"
                f" ({row['display_name']})"
                f" - {row['profile_url'] or 'profile URL unavailable'}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "### Removed Public Listings", ""])
    if removed_usernames:
        for username in removed_usernames:
            row = previous_map[username]
            lines.append(
                f"- `{username}`"
                f" ({row['display_name']})"
                f" - {row['profile_url'] or 'profile URL unavailable'}"
            )
    else:
        lines.append("- none")

    summary: dict[str, object] = {
        "current_count": len(current_snapshot),
        "previous_count": len(previous_snapshot),
        "new_count": len(added_usernames),
        "removed_count": len(removed_usernames),
        "new_usernames": added_usernames,
        "removed_usernames": removed_usernames,
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
    previous_rows = (
        _load_rows(args.previous) if args.previous is not None and args.previous.exists() else []
    )

    current_snapshot = build_snapshot(current_rows)
    previous_snapshot = build_snapshot(previous_rows)
    report, summary = build_markdown_report(current_snapshot, previous_snapshot)

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
