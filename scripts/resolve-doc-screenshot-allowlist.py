#!/usr/bin/env python3
"""Resolve the docs screenshot files that are actually referenced."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
TEXT_EXTENSIONS = {
    ".astro",
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mdx",
    ".mjs",
    ".svelte",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
}
IGNORED_DIRS = {
    ".git",
    ".github",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
IGNORED_RELATIVE_PREFIXES = {
    ("docs", "agent-logs"),
    ("docs", "screenshots", "releases"),
}
IGNORED_RELATIVE_FILES = {
    ("docs", "screenshots", "scenes.first-user.json"),
    ("docs", "screenshots", "scenes.json"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan website and docs source files for referenced docs screenshots. "
            "Optionally write a temporary capture manifest and copy a filtered "
            "current screenshot directory."
        )
    )
    parser.add_argument(
        "--website-dir",
        action="append",
        default=[],
        help="Website repository checkout to scan. Can be provided more than once.",
    )
    parser.add_argument(
        "--docs-dir",
        action="append",
        default=[],
        help="Docs repository checkout to scan. Can be provided more than once.",
    )
    parser.add_argument(
        "--hushline-dir",
        default=".",
        help="Hush Line repository checkout to scan for docs references.",
    )
    parser.add_argument(
        "--refs-input",
        help="Precomputed captureFiles JSON array to use instead of scanning source trees.",
    )
    parser.add_argument(
        "--screenshot-root",
        default="src/assets/img/screenshots",
        help="Website screenshot asset root, without the /current suffix.",
    )
    parser.add_argument(
        "--manifest-in",
        help="Base capture manifest to copy and constrain with captureFiles.",
    )
    parser.add_argument(
        "--manifest-out",
        help="Path for the generated capture manifest.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the resolved captureFiles JSON array.",
    )
    parser.add_argument(
        "--current-root",
        help="Captured release/current screenshot root to validate and filter.",
    )
    parser.add_argument(
        "--filtered-root",
        help="Destination root for the filtered screenshot tree.",
    )
    return parser.parse_args()


def compile_reference_patterns(screenshot_root: str) -> list[re.Pattern[str]]:
    current_segment = f"{screenshot_root.strip('/')}/current/"
    prefix = r"(?:^|[\"'(:\s/])(?:\.{0,2}/|/)*"
    return [
        re.compile(rf"{prefix}{re.escape(current_segment)}([^\"')\s?#]+)"),
        re.compile(rf"{prefix}(?:assets/img/)?screenshots/current/([^\"')\s?#]+)"),
        re.compile(rf"{prefix}releases/latest/([^\"')\s?#]+)"),
    ]


def is_ignored(path: Path, root: Path, screenshot_root: str) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True

    if set(parts) & IGNORED_DIRS:
        return True
    if parts in IGNORED_RELATIVE_FILES:
        return True
    if tuple(parts[: len(tuple(screenshot_root.split("/")))]) == tuple(screenshot_root.split("/")):
        return True
    return any(parts[: len(prefix)] == prefix for prefix in IGNORED_RELATIVE_PREFIXES)


def iter_text_files(root: Path, *, docs_only: bool, screenshot_root: str) -> list[Path]:
    if not root.exists():
        return []

    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_ignored(path, root, screenshot_root):
            continue
        if docs_only:
            parts = path.relative_to(root).parts
            if not parts:
                continue
            if parts[0] != "docs" and path.name != "README.md":
                continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        files.append(path)
    return files


def normalize_ref(ref: str) -> str | None:
    normalized = ref.split("#", 1)[0].split("?", 1)[0].lstrip("/")
    if "\\" in normalized or normalized.startswith("../") or "/../" in normalized:
        return None
    if Path(normalized).suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    return normalized


def collect_references(
    root: Path,
    *,
    docs_only: bool,
    patterns: list[re.Pattern[str]],
    screenshot_root: str,
) -> set[str]:
    refs = set()
    for path in iter_text_files(root, docs_only=docs_only, screenshot_root=screenshot_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for match in pattern.finditer(text):
                normalized = normalize_ref(match.group(1))
                if normalized:
                    refs.add(normalized)
    return refs


def available_images(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and not path.name.endswith("-debug.png")
    }


def write_capture_manifest(manifest_in: Path, manifest_out: Path, refs: list[str]) -> None:
    manifest = json.loads(manifest_in.read_text(encoding="utf-8"))
    manifest["captureFiles"] = refs
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def read_refs_input(refs_input: Path) -> list[str]:
    refs = json.loads(refs_input.read_text(encoding="utf-8"))
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise SystemExit(f"Expected captureFiles JSON array at {refs_input}")
    return sorted(set(refs))


def copy_filtered_current(current_root: Path, filtered_root: Path, refs: list[str]) -> None:
    available = available_images(current_root)
    missing = sorted(set(refs) - available)
    if missing:
        sys.stderr.write(
            "Referenced website/docs screenshots were not produced by the capture artifact:\n"
        )
        for ref in missing:
            sys.stderr.write(f"- {ref}\n")
        raise SystemExit(1)

    filtered_root.mkdir(parents=True, exist_ok=True)
    for ref in refs:
        src = current_root / ref
        dst = filtered_root / ref
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> int:
    args = parse_args()
    screenshot_root = args.screenshot_root.strip("/")
    patterns = compile_reference_patterns(screenshot_root)

    if args.refs_input:
        ordered_refs = read_refs_input(Path(args.refs_input))
    else:
        refs = set()
        hushline_dir = Path(args.hushline_dir)
        refs.update(
            collect_references(
                hushline_dir,
                docs_only=True,
                patterns=patterns,
                screenshot_root=screenshot_root,
            )
        )
        for docs_dir in args.docs_dir:
            refs.update(
                collect_references(
                    Path(docs_dir),
                    docs_only=True,
                    patterns=patterns,
                    screenshot_root=screenshot_root,
                )
            )
        for website_dir in args.website_dir:
            refs.update(
                collect_references(
                    Path(website_dir),
                    docs_only=False,
                    patterns=patterns,
                    screenshot_root=screenshot_root,
                )
            )
        ordered_refs = sorted(refs)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(ordered_refs, indent=2) + "\n", encoding="utf-8")

    if args.manifest_in or args.manifest_out:
        if not args.manifest_in or not args.manifest_out:
            raise SystemExit("--manifest-in and --manifest-out must be used together")
        write_capture_manifest(Path(args.manifest_in), Path(args.manifest_out), ordered_refs)

    if args.current_root or args.filtered_root:
        if not args.current_root or not args.filtered_root:
            raise SystemExit("--current-root and --filtered-root must be used together")
        copy_filtered_current(Path(args.current_root), Path(args.filtered_root), ordered_refs)
        available = len(available_images(Path(args.current_root)))
        print(
            f"Filtered current screenshot tree to {len(ordered_refs)} referenced "
            f"image(s) from {available} captured image(s)."
        )
    else:
        print(f"Resolved {len(ordered_refs)} referenced screenshot image(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
