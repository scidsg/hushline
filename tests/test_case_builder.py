from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import ChatKey, Conversation, ConversationParticipant, User


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
    assert soup.find("h2", string="Case Builder") is not None
    assert soup.title is not None
    assert soup.title.get_text().startswith("Case Builder - ")
    assert "Secure Case Builder" not in response.text
    assert soup.select_one(".case-builder-notice") is None
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
    assert str(stylesheet.get("href") or "").endswith("?v=case-builder-5")
    script = soup.find("script", src=True)
    assert script is not None
    assert str(script.get("src") or "").endswith("?v=case-builder-5")
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


def test_case_builder_explains_export_options_and_unsaved_workspace(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))
    soup = BeautifulSoup(response.text, "html.parser")
    intro = soup.select_one(".case-builder-heading > p")
    assert intro is not None
    intro_text = " ".join(intro.get_text(" ", strip=True).split())
    assert "Export your reviewed outline as a password protected PDF" in intro_text
    assert "send it to yourself, or send it to a Hush Line user" in intro_text
    assert "Your workspace is not saved automatically." in intro_text
    assert "before closing, reloading, or leaving this page" in intro_text

    controls = [control.get_text(" ", strip=True).lower() for control in soup.select("a, button")]
    assert not any("send outline" in label for label in controls)
    assert not any("confirm share" in label for label in controls)
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

    for control in soup.select('textarea, input:not([type="radio"])'):
        assert control.get("name") is None

    for control in soup.select('textarea, input[type="text"]'):
        assert control.get("autocomplete") == "off"
        assert control.get("autocapitalize") == "off"
        assert control.get("autocorrect") == "off"
        assert control.get("spellcheck") == "false"
        assert control.get("translate") == "no"


def test_case_builder_has_optional_risk_gap_and_minimum_disclosure_review(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    assert soup.find("a", href="#case-review") is not None
    assert soup.find("select", id="case-review-kind") is not None
    assert soup.find("textarea", id="case-review-description") is not None
    assert soup.find("button", id="case-review-add", attrs={"type": "button"}) is not None
    assert soup.find(id="case-review-list") is not None

    checklist_ids = (
        "case-review-incomplete",
        "case-review-sensitive",
        "case-review-consequences",
        "case-review-retaliation",
        "case-review-necessary",
        "case-review-set-aside",
    )
    for checklist_id in checklist_ids:
        assert soup.find("input", id=checklist_id, attrs={"type": "checkbox"}) is not None

    assert "You do not need to fill a gap or add more detail." in page_text
    assert "possible retaliation against me or someone else" in page_text
    assert "does not decide whether your account is complete" in page_text
    assert "assess risk, predict retaliation, or provide legal or safety advice" in page_text
    assert "which may be no disclosure at all" in page_text


def test_case_builder_has_manual_audience_narrative_and_minimum_disclosure_checklist(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    assert soup.find("a", href="#case-narrative") is not None
    assert soup.find("input", id="case-narrative-audience", attrs={"type": "text"}) is not None
    assert soup.find("input", id="case-narrative-heading", attrs={"type": "text"}) is not None
    assert soup.find("textarea", id="case-narrative-new-piece") is not None
    assert soup.find("button", id="case-narrative-add-piece", attrs={"type": "button"})
    assert soup.find(id="case-narrative-sources") is not None
    assert soup.find(id="case-narrative-list") is not None

    for checklist_id in (
        "case-narrative-include-check",
        "case-narrative-exclude-check",
        "case-narrative-hold-check",
    ):
        assert soup.find("input", id=checklist_id, attrs={"type": "checkbox"}) is not None

    assert "Prepare a working copy for the audience you have in mind." in page_text
    assert "This does not select or contact anyone." in page_text
    assert "Nothing is added automatically." in page_text
    assert "Outline edits do not rewrite source items." in page_text


def test_case_builder_next_actions_require_review_and_warn_about_export_and_sharing(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("case_builder"))
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    actions = {
        control.get("value")
        for control in soup.select('input[type="radio"][name="case-next-action"]')
    }
    assert actions == {"export_packet", "drop_tip", "send_to_self"}
    assert not soup.select_one('input[name="case-next-action"]:checked')
    assert soup.find("button", id="case-next-action-review", attrs={"type": "button"})
    review_panel = soup.find(id="case-next-action-review-panel")
    assert review_panel is not None
    assert review_panel.has_attr("hidden")
    assert soup.find("form") is None
    workspace = soup.find(attrs={"data-case-builder": True})
    assert workspace is not None
    assert workspace.get("data-counsel-url") == url_for("directory")
    assert workspace.get("data-chat-url") == url_for("inbox")
    assert workspace.get("data-tip-url") == url_for("directory")
    assert workspace.get("data-self-url") == url_for("case_builder_self")
    assert "Your private notes are not included automatically." in page_text


def test_case_builder_uses_existing_strict_csp(client: FlaskClient) -> None:
    response = client.get(url_for("case_builder"))

    directives = _csp_directives(response.headers["Content-Security-Policy"])
    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["script-src-elem"] == "'self'"
    assert directives["style-src"] == "'self' 'unsafe-inline'"
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
    assert "gapsAndRisks: []" in source
    assert "relationships: []" in source
    assert "selectedItems: []" in source
    assert "paragraph.textContent = value" in source
    assert "workspace.timelineEvents.slice().sort" in "".join(source.split())
    assert 'accessRisk: evidenceRisky.checked ? "risky" : "unmarked"' in source
    assert 'availability: evidenceMissing.checked ? "missing" : "available"' in source
    assert "narrativeDrafts: []" in source
    assert 'id: nextId("narrative-block")' in source
    assert "function reviewNextAction()" in source
    assert "Generation happens in your browser." in source
    assert "removeRelationshipsFor(record.id)" in source
    assert "removeNarrativeReferencesFor(record.id)" in source
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


def test_case_builder_self_requires_registration(client: FlaskClient) -> None:
    response = client.get(url_for("case_builder_self"))
    assert response.status_code == 302
    assert response.location == url_for("register", next=url_for("case_builder_import"))


@pytest.mark.usefixtures("_authenticated_user")
def test_case_builder_self_opens_own_profile(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("case_builder_self"))
    assert response.status_code == 302
    assert response.location == url_for("profile", username=user.primary_username.username)


@pytest.fixture()
def case_import_headers(
    client: FlaskClient, app: Flask, monkeypatch: pytest.MonkeyPatch, _authenticated_user: None
) -> dict[str, str]:
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    response = client.get(url_for("case_builder_import"))
    assert response.status_code == 200
    token = BeautifulSoup(response.text, "html.parser").find("input", attrs={"name": "csrf_token"})
    assert token is not None
    return {"X-CSRFToken": str(token.get("value"))}


@pytest.fixture()
def _case_import_key(user: User) -> None:
    db.session.add(
        ChatKey(
            user=user,
            key_version=1,
            public_key="synthetic-public-chat-key",
            public_signing_key="synthetic-public-signing-key",
            encrypted_private_key="synthetic-wrapped-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000},
            kdf_salt="synthetic-salt",
            wrapping_algorithm="AES-GCM",
        )
    )
    db.session.commit()


def test_case_import_requires_authentication(client: FlaskClient) -> None:
    response = client.get(url_for("case_builder_import"))
    assert response.status_code == 302
    assert "/login" in response.location
    assert db.session.scalar(db.select(db.func.count()).select_from(Conversation)) == 0


def test_case_import_requires_csrf_and_chat_key(
    client: FlaskClient, case_import_headers: dict[str, str]
) -> None:
    assert client.post(url_for("case_builder_import"), json={}).status_code == 400
    assert (
        client.post(
            url_for("case_builder_import"), json={}, headers=case_import_headers
        ).status_code
        == 409
    )
    assert db.session.scalar(db.select(db.func.count()).select_from(Conversation)) == 0


@pytest.mark.usefixtures("_case_import_key")
def test_case_import_creates_only_own_chat_and_reuses_it(
    client: FlaskClient, user: User, case_import_headers: dict[str, str]
) -> None:
    endpoint = url_for("case_builder_import")
    assert (
        client.post(
            endpoint, json={"content": "not accepted"}, headers=case_import_headers
        ).status_code
        == 400
    )
    response = client.post(endpoint, json={}, headers=case_import_headers)
    assert response.status_code == 200
    assert response.json is not None
    assert response.json["saved"] is False
    again = client.post(endpoint, json={}, headers=case_import_headers)
    assert again.json == response.json
    thread = db.session.scalar(db.select(Conversation))
    assert thread is not None
    assert len(thread.participants) == 1
    assert thread.participants[0].user_id == user.id
    assert not thread.messages
    assert response.headers["Cache-Control"] == "no-store, max-age=0"


@pytest.mark.usefixtures("_case_import_key")
def test_case_import_cannot_target_another_account(
    client: FlaskClient, user2: User, case_import_headers: dict[str, str]
) -> None:
    thread = Conversation()
    participant = ConversationParticipant()
    participant.user = user2
    participant.has_usable_public_key = True
    thread.participants.append(participant)
    db.session.add(thread)
    db.session.commit()
    with client.session_transaction() as state:
        state["case_builder_import_id"] = thread.public_id
    assert (
        client.post(
            url_for("case_builder_import"), json={}, headers=case_import_headers
        ).status_code
        == 403
    )
    assert not thread.messages


def test_case_import_preserves_csp(
    client: FlaskClient, case_import_headers: dict[str, str]
) -> None:
    response = client.get(url_for("case_builder_import"))
    directives = _csp_directives(response.headers["Content-Security-Policy"])
    assert directives["script-src"] == "'self'"
    assert directives["connect-src"] == "'self' data:"
    assert directives["frame-ancestors"] == "'none'"
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
