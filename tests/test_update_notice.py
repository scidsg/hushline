import json
import threading

import pytest
from flask import Flask, render_template_string
from pytest_mock import MockFixture

from hushline.config import load_config
from hushline.update_notice import (
    CHECK_INTERVAL,
    MAX_RESPONSE_BYTES,
    RELEASE_API,
    RELEASE_PAGE,
    RETRY_INTERVAL,
    ReleaseCheck,
    fetch_latest_release,
    init_app,
    version_tuple,
)


@pytest.mark.parametrize("value", ["main", "0.7.28-rc.1", "0.7", "01.2.3", "<script>", "v1.2.3/x"])
def test_unsupported_versions_are_not_compared(value: str) -> None:
    assert version_tuple(value) is None


@pytest.mark.parametrize(
    ("installed", "latest", "expected"),
    [
        ("0.7.9", "0.7.10", "0.7.10"),
        ("0.7.28", "0.7.28", None),
        ("0.8.0", "0.7.28", None),
        ("main", "0.7.28", None),
    ],
)
def test_notice_requires_a_numerically_newer_version(
    installed: str, latest: str, expected: str | None
) -> None:
    check = ReleaseCheck(fetch=lambda: latest, clock=lambda: 1)
    check._refresh()
    assert check.newer_than(installed) == expected


def test_check_is_nonblocking_and_single_flight() -> None:
    started = threading.Event()
    finish = threading.Event()
    calls = []

    def fetch() -> str:
        calls.append(1)
        started.set()
        finish.wait(timeout=5)
        return "0.7.28"

    check = ReleaseCheck(fetch=fetch)
    try:
        assert check.newer_than("0.7.27") is None
        assert started.wait(timeout=1)
        for _ in range(20):
            assert check.newer_than("0.7.27") is None
        assert calls == [1]
    finally:
        finish.set()


def test_cache_refreshes_daily_and_preserves_notice_on_failure(mocker: MockFixture) -> None:
    now = [0.0]
    fetch = mocker.Mock(side_effect=["0.7.28", OSError("unavailable")])
    check = ReleaseCheck(fetch=fetch, clock=lambda: now[0])
    check._refresh()
    now[0] = CHECK_INTERVAL - 1
    assert check.newer_than("0.7.27") == "0.7.28"
    fetch.assert_called_once()
    now[0] = CHECK_INTERVAL
    # Hold the refresh until the test explicitly completes it.
    thread = mocker.patch("hushline.update_notice.threading.Thread")
    assert check.newer_than("0.7.27") == "0.7.28"
    thread.assert_called_once()
    check._refresh()
    assert check.newer_than("0.7.27") == "0.7.28"
    assert check._next_check == CHECK_INTERVAL + RETRY_INTERVAL
    assert fetch.call_count == 2


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"{}", b"x" * (MAX_RESPONSE_BYTES + 1)])
def test_bad_release_responses_do_not_create_a_notice(raw: bytes, mocker: MockFixture) -> None:
    opener = mocker.patch("hushline.update_notice.urllib.request.build_opener").return_value
    opener.open.return_value.__enter__.return_value.read.return_value = raw
    check = ReleaseCheck()
    check._refresh()
    assert check.newer_than("0.7.27") is None


@pytest.mark.parametrize(
    ("draft", "prerelease", "tag"),
    [
        (True, False, "v0.7.28"),
        (False, True, "v0.7.28"),
        (False, False, "0.7.28-rc.1"),
        (False, False, "<script>alert(1)</script>"),
    ],
)
def test_nonstable_release_data_is_ignored(
    draft: bool, prerelease: bool, tag: str, mocker: MockFixture
) -> None:
    opener = mocker.patch("hushline.update_notice.urllib.request.build_opener").return_value
    opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(
        {"draft": draft, "prerelease": prerelease, "tag_name": tag}
    ).encode()
    assert fetch_latest_release() is None


def test_release_check_sends_only_fixed_public_metadata(mocker: MockFixture) -> None:
    factory = mocker.patch("hushline.update_notice.urllib.request.build_opener")
    factory.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(
        {
            "draft": False,
            "prerelease": False,
            "tag_name": "v0.7.28",
            "html_url": "https://attacker.invalid/",
        }
    ).encode()
    assert fetch_latest_release() == "0.7.28"
    query = factory.return_value.open.call_args.args[0]
    assert query.full_url == RELEASE_API
    assert query.data is None
    assert dict(query.header_items()) == {
        "Accept": "application/vnd.github+json",
        "User-agent": "HushLine-update-check",
    }
    assert factory.return_value.open.call_args.kwargs == {"timeout": 2}
    factory.return_value.open.return_value.__enter__.return_value.read.assert_called_once_with(
        MAX_RESPONSE_BYTES + 1
    )
    assert factory.call_args.args[0].redirect_request() is None


@pytest.mark.parametrize(
    "config",
    [
        {"TESTING": True},
        {"UPDATE_CHECK_ENABLED": False},
        {"ONION_HOSTNAME": "example.onion"},
        {"SERVER_NAME": "example.onion:80"},
    ],
)
def test_disabled_or_onion_default_never_starts_a_check(config: dict, mocker: MockFixture) -> None:
    app = Flask(__name__)
    app.config.update(config)
    init_app(app)
    check = mocker.patch.object(app.extensions["hushline_release_check"], "newer_than")
    with app.test_request_context():
        assert render_template_string("{{ hushline_update_version }}") == "None"
    check.assert_not_called()


def test_explicit_onion_opt_in_and_fixed_link(mocker: MockFixture) -> None:
    app = Flask(__name__)
    app.config.update(ONION_HOSTNAME="example.onion", UPDATE_CHECK_ENABLED=True)
    init_app(app)
    check = mocker.patch.object(
        app.extensions["hushline_release_check"], "newer_than", return_value="0.7.28"
    )
    with app.test_request_context():
        assert render_template_string(
            "{{ hushline_update_version }} {{ hushline_release_page }}"
        ) == ("0.7.28 " + RELEASE_PAGE)
    check.assert_called_once()


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("false", False)])
def test_update_check_environment_switch(value: str, expected: bool) -> None:
    assert load_config({"UPDATE_CHECK_ENABLED": value})["UPDATE_CHECK_ENABLED"] is expected
