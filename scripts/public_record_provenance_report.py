#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlparse

from hushline.public_record_refresh import (
    US_STATE_AUTHORITATIVE_SOURCES,
    US_STATE_CODES,
    PublicRecordRefreshError,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_input_path() -> Path:
    return _project_root() / "hushline" / "data" / "public_record_law_firms.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Audit public-record listing provenance and report strict-source coverage."),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_default_input_path(),
        help="Input JSON file path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional Markdown output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON summary output path.",
    )
    parser.add_argument(
        "--fail-on-non-specific",
        action="store_true",
        help="Exit non-zero when any listing fails strict provenance checks.",
    )
    return parser.parse_args()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublicRecordRefreshError(f"Input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PublicRecordRefreshError(f"Input file is not valid JSON: {path}") from exc

    if not isinstance(parsed, list):
        raise PublicRecordRefreshError(f"Input root must be a JSON array: {path}")
    if not all(isinstance(row, dict) for row in parsed):
        raise PublicRecordRefreshError(f"Input array must contain only JSON objects: {path}")

    rows: list[dict[str, Any]] = []
    for row in parsed:
        if not all(isinstance(key, str) for key in row):
            raise PublicRecordRefreshError(f"Input rows must use string keys only: {path}")
        rows.append(dict(row))
    return rows


def _normalize_url_for_compare(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl().casefold().rstrip("/")


def _has_listing_marker(url: str) -> bool:
    parsed = urlparse(url)
    query_fields = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key.casefold() == "listing" for key, _value in query_fields):
        return True
    fragment_fields = [field.strip() for field in parsed.fragment.split("&") if field.strip()]
    return any(field.split("=", 1)[0].strip().casefold() == "listing" for field in fragment_fields)


def _host_allowed(url: str, allowed_domains: frozenset[str]) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _row_issues(row: Mapping[str, object]) -> list[str]:
    issues: list[str] = []
    state_value = row.get("state")
    if not isinstance(state_value, str):
        return ["missing_state"]

    state_code = state_value.strip().upper()
    if state_code not in US_STATE_CODES:
        return ["non_us_state"]

    source_rule = US_STATE_AUTHORITATIVE_SOURCES.get(state_code)
    if source_rule is None:
        return ["missing_state_source_rule"]

    source_label = row.get("source_label")
    source_url = row.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        issues.append("missing_source_url")
        return issues

    source_url = source_url.strip()
    if source_label != source_rule["source_label"]:
        issues.append("source_label_mismatch")
    if not _host_allowed(source_url, source_rule["allowed_domains"]):
        issues.append("source_host_not_allowed")
    if _has_listing_marker(source_url):
        issues.append("synthetic_listing_marker")
    if _normalize_url_for_compare(source_url) == _normalize_url_for_compare(
        source_rule["source_url"]
    ):
        issues.append("generic_source_page")

    return issues


def _build_markdown_report(rows: list[dict[str, Any]]) -> tuple[str, dict[str, object]]:
    us_rows = [row for row in rows if str(row.get("state", "")).strip().upper() in US_STATE_CODES]
    issues_by_id: dict[int, list[str]] = {}
    for index, row in enumerate(us_rows):
        issues = _row_issues(row)
        if issues and issues != ["non_us_state"]:
            issues_by_id[index] = issues

    strict_count = len(us_rows) - len(issues_by_id)
    reason_counts = Counter(reason for reasons in issues_by_id.values() for reason in reasons)
    state_totals = Counter(str(row.get("state", "")).strip().upper() for row in us_rows)
    state_strict = Counter(
        str(us_rows[index].get("state", "")).strip().upper()
        for index in range(len(us_rows))
        if index not in issues_by_id
    )

    lines: list[str] = [
        "## Public Record Provenance Audit",
        "",
        f"- Total listings: {len(rows)}",
        f"- U.S. listings: {len(us_rows)}",
        f"- Strict per-record official sources: {strict_count}",
        f"- Listings failing strict provenance: {len(issues_by_id)}",
        "",
        "### Failure Reasons",
        "",
    ]

    if reason_counts:
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "### State Coverage (Strict)",
            "",
            "| State | Total | Strict | Failing |",
            "| --- | ---: | ---: | ---: |",
        ],
    )
    for state_code in sorted(state_totals):
        total = state_totals[state_code]
        strict = state_strict.get(state_code, 0)
        lines.append(f"| {state_code} | {total} | {strict} | {total - strict} |")

    lines.extend(["", "### Failing Listings", ""])
    if issues_by_id:
        lines.extend(
            [
                "| Name | State | Source URL | Reasons |",
                "| --- | --- | --- | --- |",
            ],
        )
        for index, issues in sorted(issues_by_id.items()):
            row = us_rows[index]
            name = str(row.get("name", "")).replace("|", "\\|")
            state_code = str(row.get("state", "")).strip().upper()
            source_url = str(row.get("source_url", "")).replace("|", "\\|")
            lines.append(f"| {name} | {state_code} | {source_url} | {', '.join(sorted(issues))} |")
    else:
        lines.append("- none")

    summary: dict[str, object] = {
        "total_listings": len(rows),
        "us_listings": len(us_rows),
        "strict_listings": strict_count,
        "failing_listings": len(issues_by_id),
        "failure_reasons": dict(sorted(reason_counts.items())),
        "state_totals": dict(sorted(state_totals.items())),
        "state_strict": dict(sorted(state_strict.items())),
    }
    return ("\n".join(lines) + "\n", summary)


def main() -> int:
    args = _parse_args()
    rows = _load_rows(args.input)
    report, summary = _build_markdown_report(rows)

    print(report, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    failing_listings = summary.get("failing_listings")
    if args.fail_on_non_specific and isinstance(failing_listings, int) and failing_listings > 0:
        raise PublicRecordRefreshError(
            "Provenance audit found listings without strict per-record official sources.",
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicRecordRefreshError as exc:
        print(f"public_record_provenance_report.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
