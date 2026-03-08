#!/usr/bin/env python3
"""Redact developer and environment metadata from persisted agent run logs."""

from __future__ import annotations

import re
import sys
from pathlib import Path

EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
USER_PATH_RE = re.compile(r"/(?:Users|home)/[^\s\"']+")
EXPECTED_ARGC = 3
KEY_REPLACEMENTS = {
    "Runner Codex config:": "Runner Codex config: [redacted]",
    "Configured git identity:": "Configured git identity: [redacted]",
    "Run log file:": "Run log file: [redacted]",
    "Global log file:": "Global log file: [redacted]",
    "workdir:": "workdir: [redacted]",
    "model:": "model: [redacted]",
    "provider:": "provider: [redacted]",
    "approval:": "approval: [redacted]",
    "sandbox:": "sandbox: [redacted]",
    "reasoning effort:": "reasoning effort: [redacted]",
    "reasoning summaries:": "reasoning summaries: [redacted]",
    "session id:": "session id: [redacted]",
}


def sanitize_text(text: str) -> str:
    sanitized_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        replacement = next(
            (value for prefix, value in KEY_REPLACEMENTS.items() if stripped.startswith(prefix)),
            None,
        )
        if replacement is not None:
            indent = line[: len(line) - len(stripped)]
            sanitized_lines.append(f"{indent}{replacement}")
            continue

        sanitized_line = EMAIL_RE.sub("[redacted-email]", line)
        sanitized_line = USER_PATH_RE.sub("[redacted-path]", sanitized_line)
        sanitized_lines.append(sanitized_line)

    return "\n".join(sanitized_lines) + ("\n" if text.endswith("\n") else "")


def main() -> int:
    if len(sys.argv) != EXPECTED_ARGC:
        print("usage: sanitize_agent_run_log.py <input> <output>", file=sys.stderr)
        return 1

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    sanitized = sanitize_text(input_path.read_text(encoding="utf-8"))
    output_path.write_text(sanitized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
