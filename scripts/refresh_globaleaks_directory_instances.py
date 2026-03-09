#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from hushline.globaleaks_directory_refresh import (
    GLOBALEAKS_SOURCE_LABEL,
    GLOBALEAKS_SOURCE_URL,
    GlobaLeaksDirectoryRefreshError,
    load_globaleaks_source_rows,
    refresh_globaleaks_directory_rows,
    render_globaleaks_refresh_summary,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_output_path() -> Path:
    return _project_root() / "hushline" / "data" / "globaleaks_instances.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the local GlobaLeaks instance artifact from a Shodan-derived export "
            "or another normalized source file."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input export path (JSON, JSONL, or CSV).",
    )
    parser.add_argument(
        "--source-label",
        default=GLOBALEAKS_SOURCE_LABEL,
        help=f"Source label stored in normalized rows (default: {GLOBALEAKS_SOURCE_LABEL}).",
    )
    parser.add_argument(
        "--source-url",
        default=GLOBALEAKS_SOURCE_URL,
        help=f"Source URL stored in normalized rows (default: {GLOBALEAKS_SOURCE_URL}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional Markdown path to write a refresh summary.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify output is already up to date without writing files.",
    )
    return parser.parse_args()


def _load_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise GlobaLeaksDirectoryRefreshError(f"Existing output root must be a JSON array: {path}")
    if not all(isinstance(row, dict) for row in parsed):
        raise GlobaLeaksDirectoryRefreshError(
            f"Existing output array must contain only JSON objects: {path}"
        )
    return [dict(row) for row in parsed]


def _serialize_rows(rows: Sequence[Mapping[str, object]]) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"


def _count_updated_rows(
    old_rows: Sequence[Mapping[str, object]],
    new_rows: Sequence[Mapping[str, object]],
) -> int:
    old_by_id = {
        str(row["id"]): dict(row)
        for row in old_rows
        if isinstance(row.get("id"), str) and row.get("id")
    }
    updated_count = 0
    for row in new_rows:
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            continue
        if row_id in old_by_id and old_by_id[row_id] != dict(row):
            updated_count += 1
    return updated_count


def main() -> int:
    args = _parse_args()
    existing_rows = _load_existing_rows(args.output)

    raw_rows = load_globaleaks_source_rows(args.input)
    refreshed_rows = refresh_globaleaks_directory_rows(
        raw_rows,
        source_label=args.source_label,
        source_url=args.source_url,
    )

    old_ids = {
        str(row["id"]) for row in existing_rows if isinstance(row.get("id"), str) and row.get("id")
    }
    new_ids = {
        str(row["id"]) for row in refreshed_rows if isinstance(row.get("id"), str) and row.get("id")
    }
    added_count = len(new_ids - old_ids)
    removed_count = len(old_ids - new_ids)
    updated_count = _count_updated_rows(existing_rows, refreshed_rows)

    summary = render_globaleaks_refresh_summary(
        source_url=args.source_url,
        total_count=len(refreshed_rows),
        added_count=added_count,
        removed_count=removed_count,
        updated_count=updated_count,
    )
    print(summary, end="")

    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(summary, encoding="utf-8")

    output_content = _serialize_rows(refreshed_rows)
    existing_content = args.output.read_text(encoding="utf-8") if args.output.exists() else ""

    if args.check and output_content != existing_content:
        raise GlobaLeaksDirectoryRefreshError(f"Output file is out of date: {args.output}")

    if not args.check and output_content != existing_content:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_content, encoding="utf-8")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GlobaLeaksDirectoryRefreshError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
