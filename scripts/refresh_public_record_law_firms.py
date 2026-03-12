#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from hushline.public_record_refresh import (
    DEFAULT_REGION_TARGETS,
    OFFICIAL_US_STATE_DISCOVERY_ADAPTERS,
    US_STATE_AUTHORITATIVE_SOURCES,
    US_STATE_CODES,
    LinkValidationFailure,
    OfficialStateDiscoveryResult,
    PublicRecordRefreshError,
    PublicRecordRefreshResult,
    build_requests_link_checker,
    discover_official_us_state_public_record_rows,
    refresh_public_record_rows,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_input_path() -> Path:
    return _project_root() / "hushline" / "data" / "public_record_law_firms.json"


def _default_roadmap_path() -> Path:
    return _project_root() / "docs" / "PUBLIC-RECORD-PROVENANCE-ROADMAP.md"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh and validate the public-record attorney directory artifact "
            "with deterministic ordering and optional link validation."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_default_input_path(),
        help="Source JSON file path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_input_path(),
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--regions",
        default="US,EU,APAC",
        help="Comma-separated regions to include (default: US,EU,APAC).",
    )
    parser.add_argument(
        "--region-target",
        action="append",
        default=[],
        help=(
            "Minimum region target in REGION=COUNT form. "
            "Repeat flag for multiple regions. Defaults to built-in minimum targets."
        ),
    )
    parser.add_argument(
        "--no-link-validation",
        action="store_true",
        help="Skip website/source URL validation.",
    )
    parser.add_argument(
        "--discover-chambers-ranked-firms",
        action="store_true",
        help="Add new attorneys from Chambers and Partners ranked public data.",
    )
    parser.add_argument(
        "--discover-official-us-state-firms",
        "--discover-official-us-state-attorneys",
        dest="discover_official_us_state_firms",
        action="store_true",
        help="Add attorneys only from explicitly implemented official U.S. state adapters.",
    )
    parser.add_argument(
        "--strict-discovery-state-coverage",
        action="store_true",
        help="Fail discovery when any selected U.S. state lacks an implemented adapter.",
    )
    parser.add_argument(
        "--max-discovered-per-region",
        type=int,
        default=10,
        help="Maximum newly discovered attorney listings to add per region (default: 10).",
    )
    parser.add_argument(
        "--drop-failing-records",
        action="store_true",
        help="Drop records that fail website/source link checks.",
    )
    parser.add_argument(
        "--allow-link-failures",
        action="store_true",
        help="Do not fail the command when broken links are detected.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=15.0,
        help="HTTP timeout for link validation.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts per URL when validating links.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional Markdown path to write a refresh summary.",
    )
    parser.add_argument(
        "--report-json-output",
        type=Path,
        default=None,
        help="Optional JSON path to write the structured refresh report.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify output is already up to date without writing files.",
    )
    return parser.parse_args()


def _parse_regions(value: str) -> list[str]:
    regions = [region.strip() for region in value.split(",") if region.strip()]
    if not regions:
        raise PublicRecordRefreshError("--regions must include at least one region")
    return regions


def _parse_region_targets(values: list[str], selected_regions: list[str]) -> dict[str, int]:
    if not values:
        missing_defaults = [
            region for region in selected_regions if region not in DEFAULT_REGION_TARGETS
        ]
        if missing_defaults:
            raise PublicRecordRefreshError(
                "Missing default region targets for: " + ", ".join(sorted(missing_defaults)),
            )
        return {region: DEFAULT_REGION_TARGETS[region] for region in selected_regions}

    targets: dict[str, int] = {}
    for value in values:
        region, sep, raw_count = value.partition("=")
        if not sep:
            raise PublicRecordRefreshError(f"Invalid --region-target value: {value!r}")
        region_name = region.strip()
        if not region_name:
            raise PublicRecordRefreshError(f"Invalid --region-target region name: {value!r}")
        try:
            count = int(raw_count)
        except ValueError as exc:
            raise PublicRecordRefreshError(
                f"Invalid --region-target count for {region_name}: {raw_count!r}",
            ) from exc

        targets[region_name] = count

    return targets


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

    normalized_rows: list[dict[str, Any]] = []
    for row in parsed:
        if not all(isinstance(key, str) for key in row):
            raise PublicRecordRefreshError(f"Input rows must use string keys only: {path}")
        normalized_rows.append({str(key): value for key, value in row.items()})
    return normalized_rows


def _serialized_rows(rows: Sequence[Mapping[str, object]]) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"


def _apply_us_state_source_strategy(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    normalized_rows: list[dict[str, object]] = []
    for raw_row in rows:
        row = dict(raw_row)
        raw_state = row.get("state")
        if not isinstance(raw_state, str):
            normalized_rows.append(row)
            continue

        state_code = raw_state.strip().upper()
        state_source = US_STATE_AUTHORITATIVE_SOURCES.get(state_code)
        if state_source is None:
            normalized_rows.append(row)
            continue

        row["source_label"] = state_source["source_label"]

        normalized_rows.append(row)

    return normalized_rows


def _diff_listing_ids(
    *,
    baseline_rows: Sequence[Mapping[str, object]],
    refreshed_rows: Sequence[Mapping[str, object]],
) -> tuple[list[str], list[str]]:
    baseline_ids = [
        row_id
        for row in baseline_rows
        for raw_id in [row.get("id")]
        if isinstance(raw_id, str)
        for row_id in [raw_id]
    ]
    baseline_id_set = set(baseline_ids)
    refreshed_id_set = {
        row_id
        for row in refreshed_rows
        for raw_id in [row.get("id")]
        if isinstance(raw_id, str)
        for row_id in [raw_id]
    }
    added_ids = [
        row_id
        for row in refreshed_rows
        for raw_id in [row.get("id")]
        if isinstance(raw_id, str)
        for row_id in [raw_id]
        if row_id not in baseline_id_set
    ]
    removed_ids = [row_id for row_id in baseline_ids if row_id not in refreshed_id_set]
    return added_ids, removed_ids


def _serialize_link_failure(failure: LinkValidationFailure) -> dict[str, str]:
    return {
        "listing_id": failure.listing_id,
        "listing_name": failure.listing_name,
        "field": failure.field,
        "url": failure.url,
        "reason": failure.reason,
    }


def _build_refresh_report(
    *,
    baseline_rows: Sequence[Mapping[str, object]],
    refresh_result: PublicRecordRefreshResult,
    selected_regions: Sequence[str],
    official_discovery_result: OfficialStateDiscoveryResult | None = None,
) -> dict[str, Any]:
    state_counts = Counter(
        state_code
        for row in refresh_result.rows
        for raw_state in [row.get("state")]
        if isinstance(raw_state, str)
        for state_code in [raw_state.strip().upper()]
        if state_code in US_STATE_CODES
    )
    per_state_counts = {
        state_code: state_counts.get(state_code, 0) for state_code in sorted(US_STATE_CODES)
    }
    covered_states = [state_code for state_code, count in per_state_counts.items() if count > 0]
    missing_states = [state_code for state_code, count in per_state_counts.items() if count == 0]
    added_ids, removed_ids = _diff_listing_ids(
        baseline_rows=baseline_rows,
        refreshed_rows=refresh_result.rows,
    )

    report: dict[str, Any] = {
        "output_records": len(refresh_result.rows),
        "total_strict_listings": sum(per_state_counts.values()),
        "states_covered": covered_states,
        "states_missing": missing_states,
        "rows_added": len(added_ids),
        "rows_removed": len(removed_ids),
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "per_state_counts": per_state_counts,
        "regional_counts": {
            region: refresh_result.region_counts.get(region, 0) for region in selected_regions
        },
        "validation_summary": {
            "unique_urls_checked": refresh_result.checked_url_count,
            "link_failures_detected": len(refresh_result.link_failures),
            "records_dropped": len(refresh_result.dropped_record_ids),
            "dropped_record_ids": list(refresh_result.dropped_record_ids),
            "link_failures": [
                _serialize_link_failure(failure) for failure in refresh_result.link_failures
            ],
        },
    }

    if official_discovery_result is not None:
        report["official_discovery"] = {
            "rows_added": len(official_discovery_result.rows),
            "added_by_state": dict(sorted(official_discovery_result.added_count_by_state.items())),
            "unsupported_states": list(official_discovery_result.unsupported_states),
        }

    return report


def _render_refresh_report_markdown(report: Mapping[str, Any]) -> str:
    states_covered = list(report["states_covered"])
    states_missing = list(report["states_missing"])
    added_ids = list(report["added_ids"])
    removed_ids = list(report["removed_ids"])
    per_state_counts = dict(report["per_state_counts"])
    regional_counts = dict(report["regional_counts"])
    validation_summary = dict(report["validation_summary"])
    link_failures = list(validation_summary["link_failures"])
    dropped_record_ids = list(validation_summary["dropped_record_ids"])

    lines = [
        "## Public Record Refresh Report",
        "",
        f"- Output records: {report['output_records']}",
        f"- Total strict U.S. listings: {report['total_strict_listings']}",
        f"- States covered: {len(states_covered)} / {len(US_STATE_CODES)}",
        (
            "- Missing states: none"
            if not states_missing
            else "- Missing states: " + ", ".join(states_missing)
        ),
        f"- Rows added: {report['rows_added']}",
        f"- Rows removed: {report['rows_removed']}",
        "- Regional counts:",
    ]
    lines.extend([f"  - {region}: {count}" for region, count in regional_counts.items()])

    lines.extend(["", "### Per-State Counts", "", "| State | Listings |", "| --- | ---: |"])
    lines.extend([f"| {state_code} | {count} |" for state_code, count in per_state_counts.items()])

    lines.extend(["", "### Dataset Drift", ""])
    if added_ids:
        lines.append("- Added IDs:")
        lines.extend([f"  - `{row_id}`" for row_id in added_ids])
    else:
        lines.append("- Added IDs: none")

    if removed_ids:
        lines.append("- Removed IDs:")
        lines.extend([f"  - `{row_id}`" for row_id in removed_ids])
    else:
        lines.append("- Removed IDs: none")

    lines.extend(
        [
            "",
            "### Validation Summary",
            "",
            f"- Unique URLs checked: {validation_summary['unique_urls_checked']}",
            f"- Link failures detected: {validation_summary['link_failures_detected']}",
            f"- Records dropped: {validation_summary['records_dropped']}",
        ],
    )
    if dropped_record_ids:
        lines.append("- Dropped IDs:")
        lines.extend([f"  - `{record_id}`" for record_id in dropped_record_ids])
    else:
        lines.append("- Dropped IDs: none")

    if link_failures:
        lines.append("- Link failures:")
        lines.extend(
            [
                (
                    f"  - `{failure['listing_id']}` `{failure['field']}` "
                    f"({failure['reason']}): {failure['url']}"
                )
                for failure in link_failures
            ],
        )
    else:
        lines.append("- Link failures: none")

    official_discovery = report.get("official_discovery")
    if isinstance(official_discovery, dict):
        added_by_state = dict(official_discovery["added_by_state"])
        unsupported_states = list(official_discovery["unsupported_states"])
        lines.extend(
            [
                "",
                "### Official Discovery",
                "",
                f"- Rows added by implemented adapters: {official_discovery['rows_added']}",
                (
                    "- U.S. states without adapters: none"
                    if not unsupported_states
                    else "- U.S. states without adapters: " + ", ".join(unsupported_states)
                ),
            ],
        )
        if added_by_state:
            lines.append("- Added rows by state:")
            lines.extend(
                [f"  - {state_code}: {count}" for state_code, count in added_by_state.items()]
            )

    return "\n".join(lines) + "\n"


def _sync_provenance_roadmap(
    path: Path,
    *,
    report: Mapping[str, Any],
    generated_on: str,
) -> None:
    content = path.read_text(encoding="utf-8")
    state_list = ", ".join(f"`{state_code}`" for state_code in report["states_covered"])
    adapter_count = len(OFFICIAL_US_STATE_DISCOVERY_ADAPTERS)
    updated = re.sub(
        r"## Current Baseline \([^)]+\)\n"
        r"- Active strict listings: `[^`]+`\n"
        r"- States with strict listings: .+\n",
        (
            f"## Current Baseline ({generated_on})\n"
            f"- Active strict listings: `{report['total_strict_listings']}`\n"
            f"- States with strict listings: {state_list or 'none'}\n"
        ),
        content,
        count=1,
    )
    updated = re.sub(
        r"^- .*explicit adapter entries in discovery code.*$",
        (
            "- Explicit state adapter entries in discovery code: "
            f"{adapter_count} / {len(US_STATE_CODES)}."
        ),
        updated,
        count=1,
        flags=re.MULTILINE,
    )
    if updated != content:
        path.write_text(updated, encoding="utf-8")


def main() -> int:
    args = _parse_args()
    selected_regions = _parse_regions(args.regions)
    region_targets = _parse_region_targets(args.region_target, selected_regions)

    link_checker = None
    if not args.no_link_validation:
        link_checker = build_requests_link_checker(
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
        )

    baseline_rows = _apply_us_state_source_strategy(_load_rows(args.input))
    source_rows = baseline_rows
    if args.discover_chambers_ranked_firms:
        raise PublicRecordRefreshError(
            "--discover-chambers-ranked-firms is disabled. "
            "Only official public sources are allowed."
        )
    official_discovery_result: OfficialStateDiscoveryResult | None = None
    if args.discover_official_us_state_firms:
        official_discovery_result = discover_official_us_state_public_record_rows(
            source_rows,
            selected_regions=selected_regions,
            max_new_per_state=args.max_discovered_per_region,
            timeout_seconds=args.timeout_seconds,
            strict_state_adapter_coverage=args.strict_discovery_state_coverage,
        )
        source_rows = [*source_rows, *[dict(row) for row in official_discovery_result.rows]]

    refresh_result = refresh_public_record_rows(
        source_rows,
        selected_regions=selected_regions,
        region_targets=region_targets,
        link_checker=link_checker,
        drop_failed_links=args.drop_failing_records,
    )
    report = _build_refresh_report(
        baseline_rows=baseline_rows,
        selected_regions=selected_regions,
        refresh_result=refresh_result,
        official_discovery_result=official_discovery_result,
    )
    summary = _render_refresh_report_markdown(report)
    print(summary, end="")

    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(summary, encoding="utf-8")
    if args.report_json_output is not None:
        args.report_json_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    output_content = _serialized_rows(refresh_result.rows)
    existing_output = args.output.read_text(encoding="utf-8") if args.output.exists() else ""

    if args.check and output_content != existing_output:
        raise PublicRecordRefreshError(f"Output file is out of date: {args.output}")

    if not args.check and output_content != existing_output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_content, encoding="utf-8")

    if (
        not args.check
        and "US" in selected_regions
        and args.input.resolve() == _default_input_path().resolve()
        and args.output.resolve() == _default_input_path().resolve()
    ):
        _sync_provenance_roadmap(
            _default_roadmap_path(),
            report=report,
            generated_on=datetime.now().astimezone().date().isoformat(),
        )

    link_failures_detected = bool(refresh_result.link_failures)
    if link_failures_detected and not args.allow_link_failures and not args.drop_failing_records:
        raise PublicRecordRefreshError(
            "Broken links detected during refresh. "
            "Use --allow-link-failures to flag only, or --drop-failing-records to remove them."
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicRecordRefreshError as exc:
        print(f"refresh_public_record_law_firms.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
