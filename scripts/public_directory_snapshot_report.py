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


class ReportSummary(TypedDict):
    current_count: int
    last_sync: DiffSummary
    last_week: DiffSummary


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
    parser.add_argument(
        "--summary-history-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory of timestamped summary JSON files used to build "
            "a historical README table."
        ),
    )
    parser.add_argument(
        "--readme-output",
        type=Path,
        default=None,
        help="Optional README Markdown output path.",
    )
    parser.add_argument(
        "--report-timestamp",
        type=str,
        default=None,
        help="Optional UTC timestamp in YYYY-MM-DDTHH-MM-SSZ form for README output.",
    )
    parser.add_argument(
        "--source-url",
        type=str,
        default=None,
        help="Optional source URL to include in the generated README.",
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

    return (
        not bool(row.get("is_public_record"))
        and not bool(row.get("is_globaleaks"))
        and not bool(row.get("is_securedrop"))
    )


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


def _format_diff_sentence(label: str, diff: DiffSummary) -> str:
    if not diff["has_baseline"]:
        return f"{label} comparison is not available yet."

    added_phrase = (
        f"{diff['new_count']} listing was added"
        if diff["new_count"] == 1
        else f"{diff['new_count']} listings were added"
    )
    removed_phrase = (
        f"{diff['removed_count']} listing was removed"
        if diff["removed_count"] == 1
        else f"{diff['removed_count']} listings were removed"
    )
    return f"{label}, {added_phrase} and {removed_phrase}."


def build_markdown_report(
    current_snapshot: list[dict[str, object]],
    previous_sync_snapshot: list[dict[str, object]] | None,
    previous_week_snapshot: list[dict[str, object]] | None,
) -> tuple[str, ReportSummary]:
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

    summary: ReportSummary = {
        "current_count": len(current_snapshot),
        "last_sync": last_sync_summary,
        "last_week": last_week_summary,
    }
    return ("\n".join(lines) + "\n", summary)


def _parse_history_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _load_summary_history(
    summary_history_dir: Path | None,
    *,
    current_timestamp: str | None = None,
    current_summary: ReportSummary | None = None,
) -> list[tuple[str, ReportSummary]]:
    rows: dict[str, ReportSummary] = {}
    if summary_history_dir is not None and summary_history_dir.exists():
        for path in summary_history_dir.glob("*.json"):
            timestamp = _parse_history_timestamp(path.stem)
            if timestamp is None:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows[path.stem] = cast(ReportSummary, payload)

    if current_timestamp is not None and current_summary is not None:
        rows[current_timestamp] = current_summary

    return sorted(
        rows.items(),
        key=lambda item: _parse_history_timestamp(item[0]) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def build_readme_report(
    summary: ReportSummary,
    *,
    report_timestamp: str,
    source_url: str,
    summary_history: list[tuple[str, ReportSummary]],
) -> str:
    timestamp = _parse_history_timestamp(report_timestamp)
    rendered_timestamp = (
        timestamp.strftime("%Y-%m-%d %H:%M UTC") if timestamp is not None else report_timestamp
    )
    sync_sentence = _format_diff_sentence("Since the last sync", summary["last_sync"])
    weekly_sentence = _format_diff_sentence(
        "Compared with the most recent snapshot at least seven days old",
        summary["last_week"],
    )
    lines = [
        "# Hush Line Stats",
        "",
        "Private operational reporting for the public Hush Line directory.",
        "",
        (
            f"As of {rendered_timestamp}, the directory contains "
            f"{summary['current_count']} opted-in public listing"
            f"{'' if summary['current_count'] == 1 else 's'}."
        ),
        sync_sentence,
        weekly_sentence,
        "",
        f"Source feed: `{source_url}`",
        "",
        "## Historical Summary",
        "",
        (
            "| Snapshot (UTC) | Listings | New vs last sync | "
            "Removed vs last sync | New vs last week | Removed vs last week |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for history_timestamp, history_summary in summary_history:
        last_sync = history_summary["last_sync"]
        last_week = history_summary["last_week"]
        last_sync_new = str(last_sync["new_count"]) if last_sync["has_baseline"] else "n/a"
        last_sync_removed = str(last_sync["removed_count"]) if last_sync["has_baseline"] else "n/a"
        last_week_new = str(last_week["new_count"]) if last_week["has_baseline"] else "n/a"
        last_week_removed = str(last_week["removed_count"]) if last_week["has_baseline"] else "n/a"
        lines.append(
            "| "
            f"{history_timestamp.replace('T', ' ').replace('Z', '')} | "
            f"{history_summary['current_count']} | "
            f"{last_sync_new} | "
            f"{last_sync_removed} | "
            f"{last_week_new} | "
            f"{last_week_removed} |"
        )

    lines.extend(
        [
            "",
            "## Latest Artifacts",
            "",
            "- `public-directory/latest.json`: normalized current public listings",
            "- `public-directory/latest-summary.json`: machine-readable latest diff summary",
            "- `public-directory/latest.md`: detailed latest report",
        ]
    )
    return "\n".join(lines) + "\n"


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
    readme = None
    if (
        args.readme_output is not None
        and args.report_timestamp is not None
        and args.source_url is not None
    ):
        summary_history = _load_summary_history(
            args.summary_history_dir,
            current_timestamp=args.report_timestamp,
            current_summary=summary,
        )
        readme = build_readme_report(
            summary,
            report_timestamp=args.report_timestamp,
            source_url=args.source_url,
            summary_history=summary_history,
        )

    print(report, end="")

    if args.snapshot_output is not None:
        _write_json(args.snapshot_output, current_snapshot)
    if args.report_output is not None:
        _write_text(args.report_output, report)
    if args.json_output is not None:
        _write_json(args.json_output, summary)
    if args.readme_output is not None and readme is not None:
        _write_text(args.readme_output, readme)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicDirectorySnapshotError as exc:
        print(f"public_directory_snapshot_report.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
