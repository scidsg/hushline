from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "weekly_agent_report_runner.py"
UTC = timezone.utc


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("weekly_agent_report_runner", RUNNER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_addresses_and_title_are_fixed() -> None:
    runner = load_runner()

    assert runner.REPORT_TITLE == "Weekly Agent Report"
    assert runner.REPORT_FROM == "weekly-report@hushline.app"
    assert runner.REPORT_TO == "glenn@hushline.app"


def test_default_sources_match_monitored_logs() -> None:
    runner = load_runner()

    paths = [source.path for source in runner.default_log_sources()]

    assert Path.home() / ".codex/logs/hushline-agent-runner.log" in paths
    assert Path.home() / "tor-code-agent/logs/tor-agent.err.log" in paths
    assert (ROOT / "../hushline-social/logs/social-daily.log") in paths


def test_collect_events_from_hushline_runner_log(tmp_path: Path) -> None:
    runner = load_runner()
    log_path = tmp_path / "hushline-agent-runner.log"
    log_path.write_text(
        "\n".join(
            [
                "[2026-05-17 10:00:00 PDT] Starting daily issue runner check.",
                (
                    "[2026-05-17 10:00:06 PDT] Skipped: no open issues found in "
                    "project 'Hush Line Roadmap' column 'Agent Eligible'."
                ),
                "[2026-05-17 11:00:00 PDT] Starting daily issue runner check.",
                "Opened PR: https://github.com/scidsg/hushline/pull/2001",
            ],
        ),
        encoding="utf-8",
    )

    events, warnings = runner.collect_events(
        [runner.LogSource("Hush Line issue runner", log_path)],
        datetime(2026, 5, 17, 16, 0, tzinfo=UTC),
    )

    assert warnings == []
    assert [event.category for event in events] == ["completed", "work", "skipped", "work"]
    assert events[0].summary == "Opened PR"
    assert events[0].detail == "https://github.com/scidsg/hushline/pull/2001"


def test_collect_events_from_social_runner_log(tmp_path: Path) -> None:
    runner = load_runner()
    log_path = tmp_path / "social-daily.log"
    log_path.write_text(
        "\n".join(
            [
                "[2026-05-15 06:10:04 PDT] Starting daily LinkedIn publisher wrapper.",
                "Published LinkedIn post for friday",
                "- post id: urn:li:share:7461040224387801089",
                "[main 713c565] Archive social post for 2026-05-15",
                (
                    "Error: Post messaging for 2026-05-15 overlaps too heavily "
                    "with recent archive 2026-05-05."
                ),
            ],
        ),
        encoding="utf-8",
    )

    events, warnings = runner.collect_events(
        [runner.LogSource("Hush Line social runner", log_path)],
        datetime(2026, 5, 15, 13, 0, tzinfo=UTC),
    )

    assert warnings == []
    assert any(event.summary == "Published LinkedIn post" for event in events)
    assert any(event.summary == "Created commit" for event in events)
    assert any(event.category == "attention" for event in events)


def test_render_report_groups_completed_attention_and_noop_events(tmp_path: Path) -> None:
    runner = load_runner()
    source = runner.LogSource("Hush Line issue runner", tmp_path / "runner.log")
    since = datetime(2026, 5, 10, 0, 0, tzinfo=UTC)
    until = datetime(2026, 5, 17, 0, 0, tzinfo=UTC)
    events = [
        runner.AgentEvent(
            timestamp=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
            source="Hush Line issue runner",
            category="completed",
            summary="Opened PR",
            detail="https://github.com/scidsg/hushline/pull/2001",
        ),
        runner.AgentEvent(
            timestamp=datetime(2026, 5, 16, 11, 0, tzinfo=UTC),
            source="Tor code agent",
            category="skipped",
            summary="No assigned issues",
            detail="No open issues assigned to glenns.",
        ),
        runner.AgentEvent(
            timestamp=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
            source="Hush Line social runner",
            category="attention",
            summary="Error: Post messaging overlaps too heavily.",
        ),
    ]

    report = runner.render_report(events, [], [source], since, until)

    assert "Weekly Agent Report" in report
    assert "From: weekly-report@hushline.app" in report
    assert "To: glenn@hushline.app" in report
    assert "Completed work events: 1" in report
    assert (
        "[Hush Line issue runner] Opened PR: " "https://github.com/scidsg/hushline/pull/2001"
    ) in report
    assert "Needs Attention:" in report
    assert "No-op Summary:" in report
    assert "Tor code agent: No assigned issues (1)" in report
    assert "Full log transcripts are not included in the email." in report


def test_send_with_mail_app_uses_native_mail_and_fixed_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> Result:
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner.send_with_mail_app("Subject", "Body")

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:2] == ["/usr/bin/osascript", "-"]
    assert command[2:5] == ["weekly-report@hushline.app", "glenn@hushline.app", "Subject"]
    script = kwargs["input"]
    assert isinstance(script, str)
    assert 'tell application "Mail"' in script
    assert "make new to recipient" in script
