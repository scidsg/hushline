import json
import os

import pytest

from hushline.config import (
    _JSON_CFG_PREFIX,
    _STRING_CFG_PREFIX,
    AliasMode,
    ConfigParseError,
    load_config,
)

CFG_NAME = "DOES_NOT_EXIST"


def test_config_parse_string() -> None:
    env = dict(**os.environ)
    value = "test-123"
    env[_STRING_CFG_PREFIX + CFG_NAME] = value

    cfg = load_config(env)
    assert cfg[CFG_NAME] == value


def test_config_parse_json() -> None:
    env = dict(**os.environ)
    value = "test-123"
    env[_JSON_CFG_PREFIX + CFG_NAME] = json.dumps(value)

    cfg = load_config(env)
    assert cfg[CFG_NAME] == value

    value_int = 123
    env[_JSON_CFG_PREFIX + CFG_NAME] = json.dumps(value_int)

    cfg = load_config(env)
    assert cfg[CFG_NAME] == value_int


def test_config_parse_json_fail() -> None:
    env = dict(**os.environ)
    key = _JSON_CFG_PREFIX + CFG_NAME
    value = "string not encoded as json"
    env[key] = value

    with pytest.raises(ConfigParseError) as e_info:
        load_config(env)
    assert key in str(e_info.value)
    assert value not in str(e_info.value)


def test_parse_alias_mode() -> None:
    assert AliasMode.parse("always") == AliasMode.ALWAYS

    with pytest.raises(ConfigParseError, match="Not a valid value"):
        AliasMode.parse("wat")


def test_preferred_url_scheme_defaults() -> None:
    env = dict(**os.environ)
    env.pop("PREFERRED_URL_SCHEME", None)
    env.pop("SERVER_NAME", None)

    cfg = load_config(env)
    assert cfg["PREFERRED_URL_SCHEME"] == "http"

    env["SERVER_NAME"] = "example.com"
    cfg = load_config(env)
    assert cfg["PREFERRED_URL_SCHEME"] == "https"


def test_preferred_url_scheme_override() -> None:
    env = dict(**os.environ)
    env["PREFERRED_URL_SCHEME"] = "http"
    env["SERVER_NAME"] = "example.com"

    cfg = load_config(env)
    assert cfg["PREFERRED_URL_SCHEME"] == "http"

    env["PREFERRED_URL_SCHEME"] = "https"
    cfg = load_config(env)
    assert cfg["PREFERRED_URL_SCHEME"] == "https"


def test_preferred_url_scheme_invalid_value() -> None:
    env = dict(**os.environ)
    env["PREFERRED_URL_SCHEME"] = "ftp"

    with pytest.raises(ConfigParseError, match="PREFERRED_URL_SCHEME must be"):
        load_config(env)


def test_smtp_notification_reply_to_loads() -> None:
    env = dict(**os.environ)
    env["NOTIFICATIONS_REPLY_TO"] = "reply@example.com"
    cfg = load_config(env)
    assert cfg["NOTIFICATIONS_REPLY_TO"] == "reply@example.com"
