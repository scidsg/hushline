import markdown
from bleach import clean
from markupsafe import Markup


def md_to_html(md: str | Markup) -> Markup:
    if isinstance(md, Markup):
        return md
    return Markup(
        clean(
            markdown.markdown(md),
            tags=[
                "p",
                "span",
                "b",
                "strong",
                "i",
                "em",
                "a",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "ul",
                "ol",
                "li",
            ],
            attributes={"a": ["href"]},
        )
    )
