from markupsafe import Markup

from hushline.md import md_to_html


def test_md_to_html_returns_markup_input_unchanged() -> None:
    html = Markup("<p>Safe</p>")

    assert md_to_html(html) is html


def test_md_to_html_sanitizes_disallowed_tags_and_keeps_links() -> None:
    rendered = md_to_html('[link](https://example.org)<script>alert("x")</script>')

    assert isinstance(rendered, Markup)
    assert '<a href="https://example.org">' in str(rendered)
    assert "<script>" not in str(rendered)
