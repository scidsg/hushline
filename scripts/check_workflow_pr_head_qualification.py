#!/usr/bin/env python3
"""Fail if workflow gh pr list/create commands use an unqualified --head."""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")
COMMAND_RE = re.compile(r"\bgh pr (list|create)\b")
FLAG_TOKEN_RE = re.compile(
    r"(?<!\S)(?P<flag>--head|--repo|-H|-R)(?:(?P<equals>=)|\s+)"
    r'(?P<token>"[^"]*"|\'[^\']*\'|\S+)',
)
HEAD_FLAG_RE = re.compile(r"(?<!\S)(?:--head|-H)(?:=|\s|$)")
REPO_FLAG_RE = re.compile(r"(?<!\S)(?:--repo|-R)(?:=|\s|$)")


def iter_command_blocks(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not COMMAND_RE.search(line):
            index += 1
            continue

        start = index
        block = [line]
        index += 1
        while index < len(lines):
            previous = block[-1].rstrip()
            current = lines[index]
            stripped = current.lstrip()
            if previous.endswith("\\") or stripped.startswith("--"):
                block.append(current)
                index += 1
                continue
            break

        blocks.append((start + 1, "\n".join(block)))
    return blocks


def extract_flag_values(command: str, flags: set[str]) -> list[str]:
    values: list[str] = []
    for match in FLAG_TOKEN_RE.finditer(command):
        if match.group("flag") not in flags:
            continue
        token = match.group("token")
        try:
            values.append(shlex.split(token)[0])
        except ValueError:
            values.append(token.strip("\"'"))
    return values


def is_unqualified_head(command: str) -> bool:
    if not REPO_FLAG_RE.search(command) or not HEAD_FLAG_RE.search(command):
        return False

    head_values = extract_flag_values(command, {"--head", "-H"})
    if not head_values:
        return True

    return any(":" not in token for token in head_values)


def main() -> int:
    violations: list[str] = []
    for workflow_path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        text = workflow_path.read_text(encoding="utf-8")
        for line_number, command in iter_command_blocks(text):
            if is_unqualified_head(command):
                violations.append(
                    f"{workflow_path}:{line_number}: gh pr command with --repo "
                    "must use owner-qualified --head",
                )

    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1

    print("All workflow gh pr commands use owner-qualified --head values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
