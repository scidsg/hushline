import typing

import pytest

from hushline.safe_template import TemplateError, safe_render_template


def test_empty() -> None:
    assert safe_render_template("", {}) == ""
    assert safe_render_template("", {"foo": "bar"}) == ""


def test_no_vars() -> None:
    assert safe_render_template("hello world", {}) == "hello world"
    assert safe_render_template("hello world", {"foo": "bar"}) == "hello world"


def test_missing_var() -> None:
    with pytest.raises(TemplateError, match="Variable not defined: name"):
        safe_render_template("hello {{ name }}", {})


def test_invalid_var_syntax() -> None:
    var_name = "invalid var syntax"
    with pytest.raises(TemplateError, match=f"Variable with invalid syntax: {var_name}"):
        safe_render_template("foo", {var_name: "bar"})


def test_unclosed_var() -> None:
    with pytest.raises(
        TemplateError, match="Invalid syntax. Variable substitution braces not closed."
    ):
        safe_render_template("{{ foo", {})


def test_unopened_var() -> None:
    with pytest.raises(TemplateError, match="Invalid syntax. Extra variable substitution braces."):
        safe_render_template("foo }}", {})


def test_invalid_var_value() -> None:
    name = "bar"
    value = typing.cast(str, 123)
    with pytest.raises(ValueError, match=f"Variable {name} was not a string: {value}"):
        safe_render_template("foo", {name: value})


def test_single_var() -> None:
    assert safe_render_template("hello {{ name }}", {"name": "world"}) == "hello world"


def test_multiple_vars() -> None:
    result = safe_render_template(
        "hello {{ name }}. my name is {{ self }}. :)", {"name": "world", "self": "bob"}
    )
    assert result == "hello world. my name is bob. :)"
