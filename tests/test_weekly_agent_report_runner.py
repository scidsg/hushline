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


def test_parse_log_timestamp_uses_timezone_abbreviation_during_fallback() -> None:
    runner = load_runner()

    pdt_timestamp, pdt_message = runner.parse_log_timestamp(
        "[2026-11-01 01:30:00 PDT] before fallback",
    )
    pst_timestamp, pst_message = runner.parse_log_timestamp(
        "[2026-11-01 01:30:00 PST] after fallback",
    )

    assert pdt_message == "before fallback"
    assert pst_message == "after fallback"
    assert pdt_timestamp == datetime(2026, 11, 1, 8, 30, tzinfo=UTC)
    assert pst_timestamp == datetime(2026, 11, 1, 9, 30, tzinfo=UTC)


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


def test_main_persists_report_body_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    output_dir = tmp_path / "reports"
    sent = []

    def fake_send(subject: str, body: str) -> None:
        sent.append((subject, body))

    monkeypatch.setenv(runner.REPORT_OUTPUT_DIR_ENV, str(output_dir))
    monkeypatch.setattr(runner, "send_with_mail_app", fake_send)

    result = runner.main(["--log-file", str(tmp_path / "missing.log")])

    reports = list(output_dir.glob("weekly-agent-report-*.txt"))
    assert result == 0
    assert len(reports) == 1
    assert "Weekly Agent Report" in reports[0].read_text(encoding="utf-8")
    assert len(sent) == 1


def test_main_dry_run_does_not_write_default_persisted_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = load_runner()
    output_dir = tmp_path / "reports"
    monkeypatch.setenv(runner.REPORT_OUTPUT_DIR_ENV, str(output_dir))

    result = runner.main(["--dry-run", "--log-file", str(tmp_path / "missing.log")])

    assert result == 0
    assert "Weekly Agent Report" in capsys.readouterr().out
    assert not output_dir.exists()


def test_main_prunes_old_persisted_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    for index in range(3):
        (output_dir / f"weekly-agent-report-2026050{index + 1}T000000Z.txt").write_text(
            "old report\n",
            encoding="utf-8",
        )

    monkeypatch.setenv(runner.REPORT_OUTPUT_DIR_ENV, str(output_dir))
    monkeypatch.setattr(runner, "send_with_mail_app", lambda _subject, _body: None)

    result = runner.main(
        [
            "--log-file",
            str(tmp_path / "missing.log"),
            "--report-retention",
            "2",
        ],
    )

    assert result == 0
    reports = sorted(path.name for path in output_dir.glob("weekly-agent-report-*.txt"))
    assert len(reports) == 2
    assert "weekly-agent-report-20260501T000000Z.txt" not in reports


def test_main_no_persist_skips_default_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    output_dir = tmp_path / "reports"

    monkeypatch.setenv(runner.REPORT_OUTPUT_DIR_ENV, str(output_dir))
    monkeypatch.setattr(runner, "send_with_mail_app", lambda _subject, _body: None)

    result = runner.main(
        [
            "--log-file",
            str(tmp_path / "missing.log"),
            "--no-persist",
        ],
    )

    assert result == 0
    assert not output_dir.exists()
