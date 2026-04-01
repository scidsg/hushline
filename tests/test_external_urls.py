from unittest.mock import patch

import pytest
from flask import Flask

from hushline.external_urls import canonical_external_url, normalize_public_base_url


def test_normalize_public_base_url_strips_trailing_slash() -> None:
    assert normalize_public_base_url("https://example.com/") == "https://example.com"


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("ftp://example.com", "PUBLIC_BASE_URL must use http or https"),
        ("https://", "PUBLIC_BASE_URL must include a host"),
        ("https://example.com/path", "PUBLIC_BASE_URL must not include a path"),
    ],
)
def test_normalize_public_base_url_rejects_invalid_values(value: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        normalize_public_base_url(value)


def test_canonical_external_url_prefers_public_base_url(app: Flask) -> None:
    app.config["SERVER_NAME"] = None
    app.config["PUBLIC_BASE_URL"] = "https://safe.example"

    with app.test_request_context("/", base_url="http://evil.example"):
        assert canonical_external_url("directory") == "https://safe.example/directory"


@pytest.mark.parametrize(
    "config_overrides",
    [
        {"TESTING": True, "DEBUG": False, "FLASK_ENV": "production"},
        {"TESTING": False, "DEBUG": True, "FLASK_ENV": "production"},
        {"TESTING": False, "DEBUG": False, "FLASK_ENV": "development"},
    ],
)
def test_canonical_external_url_falls_back_to_request_derived_url_in_dev_and_testing(
    app: Flask, config_overrides: dict[str, bool | str]
) -> None:
    app.config["SERVER_NAME"] = None
    app.config["PUBLIC_BASE_URL"] = None
    app.config["PREFERRED_URL_SCHEME"] = "https"
    app.config["TESTING"] = False
    app.config["DEBUG"] = False
    app.config["FLASK_ENV"] = "production"
    app.config.update(config_overrides)

    with (
        patch.object(app.logger, "warning") as warning_log,
        app.test_request_context("/", base_url="http://derived.example"),
    ):
        assert canonical_external_url("directory") == "https://derived.example/directory"

    warning_log.assert_called_once_with(
        "PUBLIC_BASE_URL and SERVER_NAME are unset; falling back to request-derived "
        "external URL generation in development/testing."
    )


def test_canonical_external_url_requires_canonical_config_in_production(app: Flask) -> None:
    app.config["SERVER_NAME"] = None
    app.config["PUBLIC_BASE_URL"] = None
    app.config["TESTING"] = False
    app.config["DEBUG"] = False
    app.config["FLASK_ENV"] = "production"

    with (
        app.test_request_context("/", base_url="http://evil.example"),
        pytest.raises(
            RuntimeError,
            match="Canonical external URL generation requires PUBLIC_BASE_URL or SERVER_NAME",
        ),
    ):
        canonical_external_url("directory")
