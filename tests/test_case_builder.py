from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.model import User


def _csp_directives(csp: str) -> dict[str, str]:
    return {
        directive: sources
        for directive, sources in (
            part.strip().split(" ", 1) for part in csp.split(";") if part.strip()
        )
    }


def test_case_builder_opens_without_an_account_and_does_not_create_session_state(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))

    assert response.status_code == 200
    assert "Set-Cookie" not in response.headers
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"

    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.find("h2", string="Private case workspace") is not None
    assert soup.find(attrs={"data-case-builder": True}) is not None
    assert soup.find("form") is None

    draft = soup.find("textarea", id="case-note-draft")
    assert draft is not None
    assert draft.get("name") is None
    assert draft.get("autocomplete") == "off"
    assert draft.get("autocapitalize") == "off"
    assert draft.get("autocorrect") == "off"
    assert draft.get("spellcheck") == "false"
    assert draft.get("translate") == "no"

    add_button = soup.find("button", id="case-note-add")
    assert add_button is not None
    assert add_button.get("type") == "button"
    assert soup.find(id="case-notes-empty") is not None
    assert soup.find(id="case-notes-list") is not None
    stylesheet = soup.find("link", rel="stylesheet")
    assert stylesheet is not None
    assert str(stylesheet.get("href") or "").endswith("?v=case-builder-2")
    script = soup.find("script", src=True)
    assert script is not None
    assert str(script.get("src") or "").endswith("?v=case-builder-2")
    for asset in soup.select("script[src], link[href]"):
        asset_url = str(asset.get("src") or asset.get("href") or "")
        assert asset_url.startswith("/static/")


def test_primary_navigation_opens_case_builder(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    soup = BeautifulSoup(response.text, "html.parser")

    link = soup.find("a", href=url_for("case_builder"))
    assert link is not None
    assert link.get_text(strip=True) == "Case Builder"


@pytest.mark.usefixtures("_authenticated_user")
def test_case_builder_does_not_render_authenticated_account_context(
    client: FlaskClient,
    user: User,
) -> None:
    response = client.get(url_for("case_builder"))

    assert response.status_code == 200
    assert user.primary_username.username not in response.text
    assert "data-authenticated" not in response.text
    assert "data-chat-key-session-id" not in response.text


def test_case_builder_explains_privacy_boundary_and_has_no_share_or_export_controls(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    assert "They are not submitted tips." in page_text
    assert "Hush Line does not receive or save your note text while you work." in page_text
    assert "Closing, reloading, or leaving loses it." in page_text
    assert "What Hush Line can and cannot see" in page_text
    assert "This is not encrypted or saved draft storage." in page_text
    assert "Manually copying or capturing text creates a copy outside this workspace." in page_text
    assert "cannot securely erase browser or device artifacts" in page_text

    controls = [control.get_text(" ", strip=True).lower() for control in soup.select("a, button")]
    assert not any("share" in label for label in controls)
    assert not any("export" in label for label in controls)
    assert not any("download" in label for label in controls)
    assert not any("print" in label for label in controls)
    assert not any("copy" in label for label in controls)


def test_case_builder_has_structured_mapping_controls_without_file_or_network_forms(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    assert soup.find("form") is None
    assert soup.find("input", attrs={"type": "file"}) is None
    assert soup.find("select", id="case-claim-kind") is not None
    assert soup.find("input", id="case-claim-uncertain", attrs={"type": "checkbox"}) is not None
    assert soup.find("input", id="case-event-date", attrs={"type": "date"}) is not None
    assert soup.find("input", id="case-event-approximate", attrs={"type": "checkbox"}) is not None
    assert soup.find("textarea", id="case-event-parties") is not None
    assert soup.find("textarea", id="case-event-sources") is not None
    assert soup.find("input", id="case-evidence-missing", attrs={"type": "checkbox"}) is not None
    assert soup.find("input", id="case-evidence-uncertain", attrs={"type": "checkbox"}) is not None
    assert soup.find("input", id="case-evidence-risky", attrs={"type": "checkbox"}) is not None
    assert soup.find("input", id="case-corroborator-label") is not None
    assert soup.find("select", id="case-connection-from") is not None
    assert soup.find("select", id="case-connection-to") is not None

    assert "Separate the central concerns" in page_text
    assert "Events are arranged by date automatically." in page_text
    assert "Inventory only: files cannot be attached here." in page_text
    assert "Do not seek, copy, download, or move records" in page_text
    assert "mark it risky and leave it alone" in page_text
    assert "Contact or identifying details are not required." in page_text

    for control in soup.select("textarea, input"):
        assert control.get("name") is None

    for control in soup.select('textarea, input[type="text"]'):
        assert control.get("autocomplete") == "off"
        assert control.get("autocapitalize") == "off"
        assert control.get("autocorrect") == "off"
        assert control.get("spellcheck") == "false"
        assert control.get("translate") == "no"


def test_case_builder_uses_existing_strict_csp(client: FlaskClient) -> None:
    response = client.get(url_for("case_builder"))

    directives = _csp_directives(response.headers["Content-Security-Policy"])
    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["script-src-elem"] == "'self'"
    assert directives["connect-src"] == "'self' data:"
    assert directives["frame-ancestors"] == "'none'"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "'unsafe-eval'" not in response.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" not in response.headers["Content-Security-Policy"]


def test_case_builder_is_read_only_on_the_server(client: FlaskClient) -> None:
    response = client.post(url_for("case_builder"), data={"note": "must not reach the server"})

    assert response.status_code == 405


def test_case_builder_client_keeps_workspace_in_memory_only() -> None:
    source = Path("assets/js/case-builder.js").read_text(encoding="utf-8")

    forbidden_apis = (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "caches.",
        "document.cookie",
        "window.name",
        "navigator.clipboard",
        "serviceWorker",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "BroadcastChannel",
        "postMessage",
        "console.",
        "fetch(",
        "history.",
        "location.",
        "URLSearchParams",
    )
    for forbidden_api in forbidden_apis:
        assert forbidden_api not in source

    assert "schemaVersion: 1" in source
    assert "notes: []" in source
    assert "claims: []" in source
    assert "timelineEvents: []" in source
    assert "evidenceItems: []" in source
    assert "corroborators: []" in source
    assert "relationships: []" in source
    assert "selectedItems: []" in source
    assert "paragraph.textContent = value" in source
    assert "workspace.timelineEvents.slice().sort" in source
    assert 'accessRisk: evidenceRisky.checked ? "risky" : "unmarked"' in source
    assert 'availability: evidenceMissing.checked ? "missing" : "available"' in source
    assert "removeRelationshipsFor(record.id)" in source
    assert "innerHTML" not in source
    assert 'window.addEventListener("pagehide", clearWorkspace)' in source
    assert 'window.addEventListener("pageshow"' in source


def test_case_builder_assets_are_built_and_print_content_is_suppressed() -> None:
    webpack_config = Path("webpack.config.js").read_text(encoding="utf-8")
    stylesheet = Path("assets/scss/style.scss").read_text(encoding="utf-8")

    assert '"case-builder"' in webpack_config
    assert "@media print" in stylesheet
    assert "body.case-builder-page > :not(.case-builder-print-notice)" in stylesheet
    assert "display: none !important" in stylesheet
