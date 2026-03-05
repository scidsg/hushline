#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from hushline.public_record_refresh import (
    DEFAULT_REGION_TARGETS,
    US_STATE_AUTHORITATIVE_SOURCES,
    US_STATE_CODES,
    PublicRecordRefreshError,
    build_requests_link_checker,
    discover_official_us_state_public_record_rows,
    refresh_public_record_rows,
    render_refresh_summary,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_input_path() -> Path:
    return _project_root() / "hushline" / "data" / "public_record_law_firms.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh and validate the public-record law firm directory artifact "
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
        help="Add new firms from Chambers and Partners ranked public data.",
    )
    parser.add_argument(
        "--discover-official-us-state-firms",
        action="store_true",
        help="Add firms only from explicitly implemented official U.S. state adapters.",
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
        help="Maximum newly discovered firms to add per region (default: 10).",
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


def _append_us_state_coverage_summary(
    summary: str,
    *,
    rows: Sequence[Mapping[str, object]],
    selected_regions: Sequence[str],
) -> str:
    if "US" not in selected_regions:
        return summary

    covered_states = sorted(
        {
            state
            for row in rows
            for raw_state in [row.get("state")]
            if isinstance(raw_state, str)
            for state in [raw_state.strip().upper()]
            if state in US_STATE_CODES
        },
    )
    missing_states = sorted(set(US_STATE_CODES) - set(covered_states))

    lines = [summary.rstrip(), "", "### U.S. State Coverage", ""]
    lines.append(f"- States covered: {len(covered_states)} / {len(US_STATE_CODES)}")
    if missing_states:
        lines.append(f"- Missing states: {', '.join(missing_states)}")
    else:
        lines.append("- Missing states: none")

    return "\n".join(lines) + "\n"


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

    source_rows = _apply_us_state_source_strategy(_load_rows(args.input))
    if args.discover_chambers_ranked_firms:
        raise PublicRecordRefreshError(
            "--discover-chambers-ranked-firms is disabled. "
            "Only official public sources are allowed."
        )
    official_discovery_unsupported_states: tuple[str, ...] = ()
    official_discovery_added_count = 0
    if args.discover_official_us_state_firms:
        official_discovery_result = discover_official_us_state_public_record_rows(
            source_rows,
            selected_regions=selected_regions,
            max_new_per_state=args.max_discovered_per_region,
            timeout_seconds=args.timeout_seconds,
            strict_state_adapter_coverage=args.strict_discovery_state_coverage,
        )
        source_rows = [*source_rows, *[dict(row) for row in official_discovery_result.rows]]
        official_discovery_added_count = len(official_discovery_result.rows)
        official_discovery_unsupported_states = official_discovery_result.unsupported_states

    refresh_result = refresh_public_record_rows(
        source_rows,
        selected_regions=selected_regions,
        region_targets=region_targets,
        link_checker=link_checker,
        drop_failed_links=args.drop_failing_records,
    )
    summary = render_refresh_summary(refresh_result, regions=selected_regions)
    summary = _append_us_state_coverage_summary(
        summary,
        rows=refresh_result.rows,
        selected_regions=selected_regions,
    )
    if args.discover_official_us_state_firms:
        summary_lines = [summary.rstrip(), "", "### Official Discovery", ""]
        summary_lines.append(
            f"- Rows added by implemented adapters: {official_discovery_added_count}"
        )
        if official_discovery_unsupported_states:
            summary_lines.append(
                "- U.S. states without adapters: "
                + ", ".join(official_discovery_unsupported_states),
            )
        else:
            summary_lines.append("- U.S. states without adapters: none")
        summary = "\n".join(summary_lines) + "\n"
    print(summary, end="")

    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(summary, encoding="utf-8")

    output_content = _serialized_rows(refresh_result.rows)
    existing_output = args.output.read_text(encoding="utf-8") if args.output.exists() else ""

    if args.check and output_content != existing_output:
        raise PublicRecordRefreshError(f"Output file is out of date: {args.output}")

    if not args.check and output_content != existing_output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_content, encoding="utf-8")

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
