from unittest.mock import MagicMock

import pytest

from hushline import content_safety


def test_contains_disallowed_text_rejects_empty_input() -> None:
    assert content_safety.contains_disallowed_text(None) is False
    assert content_safety.contains_disallowed_text("") is False


def test_contains_disallowed_text_applies_allowlist_before_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    class _FakeEngine:
        @staticmethod
        def contains_profanity(text: str) -> bool:
            seen.append(text)
            return "blocked-token" in text

    monkeypatch.setenv("HUSHLINE_CONTENT_FILTER_ALLOWLIST", "ALLOW-ME")
    monkeypatch.setattr(content_safety, "_profanity_engine", lambda: _FakeEngine())

    assert content_safety.contains_disallowed_text("ALLOW-ME") is False
    assert seen
    assert "allow-me" not in seen[-1]
    assert content_safety.contains_disallowed_text("blocked-token") is True


def test_profanity_engine_returns_none_and_logs_once_when_library_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_safety._profanity_engine.cache_clear()
    content_safety._log_missing_library_once.cache_clear()

    warning = MagicMock()
    monkeypatch.setattr(content_safety, "profanity", None)
    monkeypatch.setattr(content_safety._logger, "warning", warning)

    assert content_safety._profanity_engine() is None
    assert content_safety._profanity_engine() is None
    warning.assert_called_once()


def test_contains_disallowed_text_returns_false_when_engine_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(content_safety, "_profanity_engine", lambda: None)
    assert content_safety.contains_disallowed_text("blocked-token") is False


def test_profanity_engine_loads_library_wordlist(monkeypatch: pytest.MonkeyPatch) -> None:
    content_safety._profanity_engine.cache_clear()
    content_safety._log_missing_library_once.cache_clear()

    class _FakeProfanity:
        def __init__(self) -> None:
            self.loaded = False

        def load_censor_words(self) -> None:
            self.loaded = True

        @staticmethod
        def contains_profanity(text: str) -> bool:
            return "blocked-token" in text

    fake_profanity = _FakeProfanity()
    monkeypatch.setattr(content_safety, "profanity", fake_profanity)

    engine = content_safety._profanity_engine()
    assert engine is fake_profanity
    assert fake_profanity.loaded is True
