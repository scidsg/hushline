import pytest
from flask import Flask

from hushline.utils import if_not_none, parse_bool, redirect_to_self


def test_redirect_to_self_uses_current_endpoint_and_view_args(app: Flask) -> None:
    @app.route("/test-redirect/<username>")
    def _test_redirect(username: str) -> object:
        _ = username
        return redirect_to_self()

    client = app.test_client()
    response = client.get("/test-redirect/demo")

    assert response.status_code == 302
    assert response.location == "/test-redirect/demo"


def test_if_not_none_applies_to_falsey_values_by_default() -> None:
    assert if_not_none("", lambda value: value + "z") == "z"


def test_parse_bool_false_and_invalid_values() -> None:
    assert parse_bool("false") is False

    with pytest.raises(ValueError, match="Unparseable boolean value: 'maybe'"):
        parse_bool("maybe")
