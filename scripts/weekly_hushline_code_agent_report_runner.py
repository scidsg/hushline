#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zoneinfo import ZoneInfo

REPORT_TITLE = "Weekly Agent Report"
REPORT_FROM = "weekly-report@hushline.app"
REPORT_TO = "glenn@hushline.app"
DEFAULT_LOOKBACK_DAYS = 7
LOG_FILES_ENV = "HUSHLINE_WEEKLY_AGENT_REPORT_LOG_FILES"
REPORT_OUTPUT_DIR_ENV = "HUSHLINE_WEEKLY_AGENT_REPORT_OUTPUT_DIR"
REPORT_RETENTION_ENV = "HUSHLINE_WEEKLY_AGENT_REPORT_RETENTION"
DEFAULT_REPORT_RETENTION = 12
LOCAL_TZ = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc
LOG_TIMEZONES = {
    "PDT": timezone(timedelta(hours=-7), "PDT"),
    "PST": timezone(timedelta(hours=-8), "PST"),
}
MIN_PRINTABLE_CODEPOINT = 32
MAX_COMPLETED_EVENTS = 40
MAX_ATTENTION_EVENTS = 30
MAIL_APP_APPLESCRIPT_TIMEOUT_SECONDS = 300
MAIL_APP_OSASCRIPT_TIMEOUT_SECONDS = MAIL_APP_APPLESCRIPT_TIMEOUT_SECONDS + 30
MAIL_APP_APPLE_EVENT_TIMEOUT_CODE = "-1712"

MAIL_APP_APPLESCRIPT = r"""
on run argv
  set fromAddress to item 1 of argv
  set toAddress to item 2 of argv
  set messageSubject to item 3 of argv
  set bodyPath to item 4 of argv
  set messageBody to read POSIX file bodyPath

  with timeout of 300 seconds
    tell application "Mail"
      set matchingAccount to missing value
      repeat with mailAccount in every account
        if (email addresses of mailAccount) contains fromAddress then
          set matchingAccount to mailAccount
          exit repeat
        end if
      end repeat
      if matchingAccount is missing value then
        error "Mail account not found for " & fromAddress
      end if

      set reportMessage to make new outgoing message
      set subject of reportMessage to messageSubject
      set content of reportMessage to messageBody
      set visible of reportMessage to false
      tell reportMessage
        set sender to fromAddress
        make new to recipient at end of to recipients with properties {address:toAddress}
        ignoring application responses
          send
        end ignoring
      end tell
    end tell
  end timeout
end run
"""


@dataclass(frozen=True)
class LogSource:
    name: str
    path: Path


@dataclass(frozen=True)
class AgentEvent:
    timestamp: datetime
    source: str
    category: str
    summary: str
    detail: str = ""


class RunnerError(Exception):
    """Raised when the report runner cannot complete safely."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a weekly summary of local agent runner work through Mail.app.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Number of days to include in the report. Default: {DEFAULT_LOOKBACK_DAYS}.",
    )
    parser.add_argument(
        "--log-file",
        action="append",
        type=Path,
        default=[],
        help=(
            "Log file to scan. Can be repeated. Defaults to the local Hush Line, "
            f"Tor code agent, and social runner logs, or paths from {LOG_FILES_ENV}."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report instead of sending it through Mail.app.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the generated report body to this path.",
    )
    parser.add_argument(
        "--report-output-dir",
        type=Path,
        help=(
            "Directory for persisted weekly report bodies. Defaults to "
            f"{REPORT_OUTPUT_DIR_ENV} or logs/weekly-agent-reports."
        ),
    )
    parser.add_argument(
        "--report-retention",
        type=int,
        default=int(os.environ.get(REPORT_RETENTION_ENV, DEFAULT_REPORT_RETENTION)),
        help=(
            "Number of persisted weekly report files to keep. Set to 0 to disable pruning. "
            f"Default: {DEFAULT_REPORT_RETENTION}."
        ),
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write the default persisted report artifact.",
    )
    return parser.parse_args(argv)


def normalize_text(value: object, max_length: int = 260) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = "".join(ch for ch in text if ch == "\t" or ord(ch) >= MIN_PRINTABLE_CODEPOINT)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_log_sources() -> list[LogSource]:
    env_value = os.environ.get(LOG_FILES_ENV, "")
    if env_value:
        return [
            LogSource(path.name, path)
            for path in (Path(item).expanduser() for item in env_value.split(os.pathsep) if item)
        ]

    root = repo_root()
    return [
        LogSource(
            "Hush Line issue runner",
            Path.home() / ".codex/logs/hushline-code-agent.log",
        ),
        LogSource("Tor code agent", Path.home() / "tor-code-agent/logs/tor-agent.err.log"),
        LogSource("Hush Line social runner", (root / "../hushline-social/logs/social-daily.log")),
    ]


def resolved_log_sources(cli_paths: list[Path]) -> list[LogSource]:
    sources = (
        [LogSource(path.name, path.expanduser()) for path in cli_paths]
        if cli_paths
        else default_log_sources()
    )
    resolved: list[LogSource] = []
    seen: set[Path] = set()
    for source in sources:
        path = source.path.expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        resolved.append(LogSource(source.name, path))
    return resolved


def parse_log_timestamp(line: str) -> tuple[datetime | None, str]:
    match = re.match(
        r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (PDT|PST)\]\s*(.*)$",
        line,
    )
    if not match:
        return None, line
    timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=LOG_TIMEZONES[match.group(2)],
    )
    return timestamp.astimezone(UTC), match.group(3)


def read_source_lines(source: LogSource) -> list[tuple[datetime | None, str]]:
    if not source.path.exists():
        return []
    events: list[tuple[datetime | None, str]] = []
    current_timestamp: datetime | None = None
    for line in source.path.read_text(encoding="utf-8", errors="replace").splitlines():
        timestamp, message = parse_log_timestamp(line)
        if timestamp is not None:
            current_timestamp = timestamp
        events.append((current_timestamp, normalize_text(message)))
    return events


def pr_event(source: str, timestamp: datetime, line: str) -> AgentEvent | None:
    match = re.search(r"(Opened|Updated) PR:\s*(https://github\.com/\S+)", line)
    if match:
        return AgentEvent(timestamp, source, "completed", f"{match.group(1)} PR", match.group(2))
    match = re.search(r"https://github\.com/[^ ]+/pull/\d+", line)
    if match and "/pull/new/" not in match.group(0):
        return AgentEvent(timestamp, source, "completed", "Referenced pull request", match.group(0))
    return None


def commit_event(source: str, timestamp: datetime, line: str) -> AgentEvent | None:
    match = re.match(r"^\[[^\]]+\s+[0-9a-f]{7,40}\]\s+(.+)$", line)
    if match:
        return AgentEvent(timestamp, source, "completed", "Created commit", match.group(1))
    return None


def classify_line(source: str, timestamp: datetime, line: str) -> AgentEvent | None:
    if not line:
        return None

    event = pr_event(source, timestamp, line) or commit_event(source, timestamp, line)
    if event is not None:
        return event

    if "Published LinkedIn post" in line:
        return AgentEvent(timestamp, source, "completed", "Published LinkedIn post", line)
    if line.startswith("Validated daily plan for "):
        return AgentEvent(timestamp, source, "completed", "Validated social plan", line)
    if line.startswith("Prepared daily planning context for "):
        return AgentEvent(timestamp, source, "work", "Prepared social planning context", line)
    if line.startswith("Synced latest screenshots into "):
        return AgentEvent(timestamp, source, "work", "Synced screenshots", line)
    if line.startswith("Archive push skipped."):
        return AgentEvent(timestamp, source, "skipped", "Archive push skipped", "")
    if line.startswith("Skipped:"):
        return AgentEvent(timestamp, source, "skipped", line, "")
    if "No open issues assigned to " in line:
        return AgentEvent(timestamp, source, "skipped", "No assigned issues", line)
    if line.startswith("No open issues assigned to "):
        return AgentEvent(timestamp, source, "skipped", "No assigned issues", line)
    if line.startswith("No open issues found "):
        return AgentEvent(timestamp, source, "skipped", "No eligible issues", line)
    if line.startswith("Reconciling "):
        return AgentEvent(timestamp, source, "work", "Checked project queue", line)
    if line.startswith("Starting "):
        return AgentEvent(timestamp, source, "work", line, "")
    if line.startswith("Retrying "):
        return AgentEvent(timestamp, source, "work", line, "")
    if line.startswith("Blocked:"):
        return AgentEvent(timestamp, source, "attention", line, "")
    if line.startswith(("Error:", "fatal:")) or "Traceback (most recent call last)" in line:
        return AgentEvent(timestamp, source, "attention", line, "")
    return None


def collect_events(sources: list[LogSource], since: datetime) -> tuple[list[AgentEvent], list[str]]:
    events: list[AgentEvent] = []
    warnings: list[str] = []
    for source in sources:
        if not source.path.exists():
            warnings.append(f"{source.name}: missing log file at {source.path}")
            continue
        for timestamp, line in read_source_lines(source):
            if timestamp is None or timestamp < since:
                continue
            event = classify_line(source.name, timestamp, line)
            if event is not None:
                events.append(event)
    return sorted(events, key=event_sort_key), warnings


def event_sort_key(event: AgentEvent) -> tuple[float, int]:
    category_priority = {
        "attention": 0,
        "completed": 1,
        "work": 2,
        "skipped": 3,
    }
    return (-event.timestamp.timestamp(), category_priority.get(event.category, 9))


def event_line(event: AgentEvent) -> str:
    detail = f": {event.detail}" if event.detail else ""
    timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M UTC")
    return f"- {timestamp} [{event.source}] {event.summary}{detail}"


def summarize_repeated(events: list[AgentEvent]) -> list[str]:
    counts: Counter[tuple[str, str]] = Counter((event.source, event.summary) for event in events)
    lines = []
    for (source, summary), count in sorted(counts.items()):
        lines.append(f"- {source}: {summary} ({count})")
    return lines


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    label = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {label}"


def unique_in_order(items: list[str]) -> list[str]:
    unique_items = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items


PAIR_LENGTH = 2


def human_join(items: list[str], limit: int = 4, overflow_label: str = "more") -> str:
    visible_items = items[:limit]
    remaining = len(items) - len(visible_items)
    if remaining > 0:
        visible_items.append(f"{remaining} {overflow_label}")
    if not visible_items:
        return ""
    if len(visible_items) == 1:
        return visible_items[0]
    if len(visible_items) == PAIR_LENGTH:
        return " and ".join(visible_items)
    return ", ".join(visible_items[:-1]) + f", and {visible_items[-1]}"


def sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def event_description(event: AgentEvent) -> str:
    summary = event.summary.rstrip(".")
    detail = f": {event.detail.rstrip('.')}" if event.detail else ""
    return f"{event.source} - {summary}{detail}"


def pr_descriptions(events: list[AgentEvent]) -> list[str]:
    actions = {
        "Opened PR": "opened",
        "Updated PR": "updated",
        "Referenced pull request": "referenced",
    }
    descriptions = []
    for event in events:
        action = actions.get(event.summary)
        if action is None:
            continue
        pr_number = ""
        match = re.search(r"/pull/(\d+)", event.detail)
        if match:
            pr_number = f" #{match.group(1)}"
        descriptions.append(f"{action} PR{pr_number} ({event.detail})")
    return descriptions


def linkedin_post_labels(events: list[AgentEvent]) -> list[str]:
    labels = []
    for event in events:
        if event.summary != "Published LinkedIn post":
            continue
        match = re.search(r"Published LinkedIn post for (.+)$", event.detail)
        labels.append(match.group(1) if match else event.detail)
    return labels


def render_executive_summary(
    completed: list[AgentEvent],
    work: list[AgentEvent],
    skipped: list[AgentEvent],
    attention: list[AgentEvent],
    warnings: list[str],
) -> list[str]:
    total_events = len(completed) + len(work) + len(skipped) + len(attention)
    if total_events == 0 and not warnings:
        return ["No local runner activity or log warnings were detected in this reporting window."]

    paragraphs = [
        (
            "The monitored local runners recorded "
            f"{pluralize(total_events, 'notable event')}: "
            f"{pluralize(len(completed), 'completed work item')}, "
            f"{pluralize(len(work), 'work/check item')}, "
            f"{pluralize(len(skipped), 'no-op item')}, and "
            f"{pluralize(len(attention), 'attention item')}."
        ),
    ]

    if completed:
        latest_completed = completed[0]
        completed_parts = []
        linkedin_labels = linkedin_post_labels(completed)
        if linkedin_labels:
            completed_parts.append(
                "the social runner published LinkedIn posts for "
                f"{human_join(unique_in_order(linkedin_labels), overflow_label='more posts')}"
            )
        prs = pr_descriptions(completed)
        if prs:
            completed_parts.append(f"PR activity included {human_join(prs, limit=3)}")
        else:
            completed_parts.append("no pull requests were opened or updated")
        completed_parts.append(
            "the most recent completed item was " f"{event_description(latest_completed)}"
        )
        paragraphs.append(sentence("Completed work: " + "; ".join(completed_parts)))
    else:
        paragraphs.append("No completed runner work was detected in this window.")

    if attention:
        attention_items = unique_in_order([event_description(event) for event in attention])
        paragraphs.append(
            sentence(
                "Review is needed for "
                f"{human_join(attention_items, limit=3, overflow_label='more items')}"
            )
        )
    else:
        paragraphs.append("No attention items were detected.")

    if warnings:
        paragraphs.append(
            sentence(
                f"There {'was' if len(warnings) == 1 else 'were'} "
                f"{pluralize(len(warnings), 'log source warning')} to check below"
            )
        )
    return paragraphs


def render_report(
    events: list[AgentEvent],
    warnings: list[str],
    sources: list[LogSource],
    since: datetime,
    until: datetime,
) -> str:
    grouped: dict[str, list[AgentEvent]] = defaultdict(list)
    for event in events:
        grouped[event.category].append(event)

    completed = grouped["completed"]
    work = grouped["work"]
    skipped = grouped["skipped"]
    attention = grouped["attention"]

    lines = [
        REPORT_TITLE,
        "",
        f"Window: {since.strftime('%Y-%m-%d %H:%M UTC')} to {until.strftime('%Y-%m-%d %H:%M UTC')}",
        f"From: {REPORT_FROM}",
        f"To: {REPORT_TO}",
        "",
        "Executive Summary:",
        *render_executive_summary(completed, work, skipped, attention, warnings),
        "",
        "Overview:",
        f"- Log files configured: {len(sources)}",
        f"- Events found: {len(events)}",
        f"- Completed work events: {len(completed)}",
        f"- Work/check events: {len(work)}",
        f"- Skipped/no-op events: {len(skipped)}",
        f"- Attention events: {len(attention)}",
    ]

    if warnings:
        lines.extend(["", "Log Warnings:"])
        lines.extend(f"- {warning}" for warning in warnings)

    lines.extend(["", "Completed Work:"])
    if completed:
        lines.extend(event_line(event) for event in completed[:MAX_COMPLETED_EVENTS])
        if len(completed) > MAX_COMPLETED_EVENTS:
            lines.append(
                f"- ... {len(completed) - MAX_COMPLETED_EVENTS} more completed work event(s)",
            )
    else:
        lines.append("- No completed runner work was detected in this window.")

    if attention:
        lines.extend(["", "Needs Attention:"])
        lines.extend(event_line(event) for event in attention[:MAX_ATTENTION_EVENTS])
        if len(attention) > MAX_ATTENTION_EVENTS:
            lines.append(
                f"- ... {len(attention) - MAX_ATTENTION_EVENTS} more attention event(s)",
            )

    if skipped:
        lines.extend(["", "No-op Summary:"])
        lines.extend(summarize_repeated(skipped))

    if work:
        lines.extend(["", "Work/Check Summary:"])
        lines.extend(summarize_repeated(work))

    lines.extend(["", "Log Sources:"])
    for source in sources:
        lines.append(f"- {source.name}: {source.path}")

    lines.extend(
        [
            "",
            "Notes:",
            "- This report summarizes the local runner logs you monitor on this machine.",
            "- Full log transcripts are not included in the email.",
            "- Delivery is restricted to Mail.app using the fixed sender and recipient above.",
        ],
    )
    return "\n".join(lines) + "\n"


def write_output(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def default_report_output_dir() -> Path:
    env_value = os.environ.get(REPORT_OUTPUT_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return repo_root() / "logs" / "weekly-agent-reports"


def persisted_report_path(output_dir: Path, until: datetime) -> Path:
    return output_dir / f"weekly-agent-report-{until.strftime('%Y%m%dT%H%M%SZ')}.txt"


def prune_persisted_reports(output_dir: Path, retention_count: int) -> None:
    if retention_count <= 0 or not output_dir.exists():
        return
    reports = sorted(
        output_dir.glob("weekly-agent-report-*.txt"),
        key=lambda path: path.name,
        reverse=True,
    )
    for report_path in reports[retention_count:]:
        report_path.unlink(missing_ok=True)


def send_with_mail_app(subject: str, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as temp:
        temp.write(body)
        body_path = temp.name
    try:
        command = ["/usr/bin/osascript", "-", REPORT_FROM, REPORT_TO, subject, body_path]
        try:
            result = subprocess.run(
                command,  # noqa: S603 - fixed executable; message data is passed by args/file.
                input=MAIL_APP_APPLESCRIPT,
                capture_output=True,
                text=True,
                check=False,
                timeout=MAIL_APP_OSASCRIPT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            print(
                "Warning: Mail.app send handoff exceeded the osascript timeout; "
                "the persisted report is available if delivery needs manual confirmation.",
                file=sys.stderr,
            )
            return
    finally:
        Path(body_path).unlink(missing_ok=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no Mail.app output"
        if is_mail_app_apple_event_timeout(detail):
            print(
                "Warning: Mail.app reported an AppleEvent timeout after the send handoff; "
                "the persisted report is available if delivery needs manual confirmation.",
                file=sys.stderr,
            )
            return
        raise RunnerError(f"Mail.app send failed: {detail}")


def is_mail_app_apple_event_timeout(detail: str) -> bool:
    normalized_detail = detail.lower()
    return (
        MAIL_APP_APPLE_EVENT_TIMEOUT_CODE in detail
        and "appleevent timed out" in normalized_detail
        and "mail got an error" in normalized_detail
    )


def build_subject(since: datetime, until: datetime) -> str:
    return f"{REPORT_TITLE}: {since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.lookback_days < 1:
        raise RunnerError("--lookback-days must be at least 1")
    if args.report_retention < 0:
        raise RunnerError("--report-retention must be at least 0")

    until = datetime.now(UTC)
    since = until - timedelta(days=args.lookback_days)
    sources = resolved_log_sources(args.log_file)
    events, warnings = collect_events(sources, since)
    body = render_report(events, warnings, sources, since, until)
    subject = build_subject(since, until)

    if args.output:
        write_output(args.output, body)
    persisted_path: Path | None = None
    if not args.no_persist and not args.dry_run:
        output_dir = (args.report_output_dir or default_report_output_dir()).expanduser().resolve()
        persisted_path = persisted_report_path(output_dir, until)
        write_output(persisted_path, body)
        prune_persisted_reports(output_dir, args.report_retention)
    if args.dry_run:
        print(body, end="")
    else:
        send_with_mail_app(subject, body)
        print(f"Sent {REPORT_TITLE} from {REPORT_FROM} to {REPORT_TO}.")
        if persisted_path is not None:
            print(f"Persisted report: {persisted_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
