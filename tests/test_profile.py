from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from helpers import get_profile_submission_data
from sqlalchemy.exc import MultipleResultsFound
from werkzeug.exceptions import NotFound

from hushline.db import db
from hushline.model import AccountCategory, Message, OrganizationSetting, User, Username

msg_contact_method = "I prefer Signal."
msg_content = "This is a test message."

pgp_message_sig = "-----BEGIN PGP MESSAGE-----\n\n"


@pytest.mark.usefixtures("_pgp_user")
def test_profile_header(client: FlaskClient, user: User) -> None:
    assert (
        db.session.scalars(
            db.select(OrganizationSetting).filter_by(
                key=OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE
            )
        ).one_or_none()
        is None
    )  # precondition

    resp = client.get(url_for("profile", username=user.primary_username.username))
    assert resp.status_code == 200
    assert (
        "Submit a message to "
        + (user.primary_username.display_name or user.primary_username.username)
        in resp.text
    )

    rand = str(uuid4())
    template = rand + " {{ display_name_or_username }} {{ username }} {{ display_name }}"
    OrganizationSetting.upsert(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE, template)
    db.session.commit()

    expected = (
        f"{rand} {user.primary_username.display_name or user.primary_username.username} "
        f"{user.primary_username.username} {user.primary_username.display_name or ''}"
    )
    resp = client.get(url_for("profile", username=user.primary_username.username))
    assert resp.status_code == 200
    assert expected in resp.text


def test_profile_accepts_case_insensitive_username(
    client: FlaskClient, user_alias: Username
) -> None:
    alt_username = user_alias.username.upper()
    response = client.get(url_for("profile", username=alt_username))
    assert response.status_code == 200
    assert user_alias.username in response.text


def test_profile_404_for_unknown_username(client: FlaskClient) -> None:
    response = client.get(url_for("profile", username="does-not-exist"), follow_redirects=True)
    assert response.status_code == 404
    assert "404: Not Found" in response.text


def test_profile_404s_when_case_insensitive_lookup_is_ambiguous(app: Flask) -> None:
    with (
        patch(
            "hushline.routes.profile.db.session.scalars",
            return_value=MagicMock(
                one_or_none=MagicMock(side_effect=MultipleResultsFound),
            ),
        ),
        app.test_request_context("/to/CaseUser"),
        pytest.raises(NotFound),
    ):
        app.view_functions["profile"]("CaseUser")


@pytest.mark.usefixtures("_pgp_user")
def test_profile_does_not_expose_owner_user_id(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("input", attrs={"name": "username_user_id"}) is None
    assert soup.find("input", attrs={"name": "encrypted_email_body", "type": "hidden"}) is not None

    nonce_input = soup.find("input", attrs={"name": "owner_guard_nonce"})
    signature_input = soup.find("input", attrs={"name": "owner_guard_signature"})
    captcha_input = soup.find("input", attrs={"name": "captcha_answer", "id": "captcha_answer"})
    assert nonce_input is not None
    assert signature_input is not None
    assert captcha_input is not None
    assert nonce_input.get("value")
    assert signature_input.get("value")
    assert captcha_input.get("value") in (None, "")


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_submit_message(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_submit_message_to_alias(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    response = client.post(
        url_for("profile", username=user_alias.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user_alias.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(db.select(Message).filter_by(username_id=user_alias.id)).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_failed_submit_preserves_input(client: FlaskClient, user: User) -> None:
    username = user.primary_username.username
    submission_data = get_profile_submission_data(client, username)
    submission_data["captcha_answer"] = "0"

    response = client.post(
        url_for("profile", username=username),
        data={
            "field_0": "Contact info preserved",
            "field_1": "Message preserved",
            **submission_data,
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "Invalid CAPTCHA answer" in response.text
    assert "Contact info preserved" in response.text
    assert "Message preserved" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_rejects_owner_guard_mismatch(client: FlaskClient, user: User) -> None:
    username = user.primary_username.username
    submission_data = get_profile_submission_data(client, username)
    submission_data["owner_guard_signature"] = "tampered-signature"

    response = client.post(
        url_for("profile", username=username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **submission_data,
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "tip line changed" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_pgp_required(client: FlaskClient, app: Flask, user: User) -> None:
    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    assert 'id="messageForm"' in response.text
    assert 'data-submit-spinner="true"' in response.text
    assert "You can't send encrypted messages to this user through Hush Line" not in response.text

    user.pgp_key = None
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert "Sending messages is disabled" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_post_rejects_when_target_has_no_pgp_key(client: FlaskClient, user: User) -> None:
    user.pgp_key = None
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "cannot submit messages to users who have not set a PGP key" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_post_form_validation_errors_are_rendered(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": "",
            "field_1": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "There was an error submitting your message" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_requires_csrf_token(app: Flask, client: FlaskClient, user: User) -> None:
    prior = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **get_profile_submission_data(client, user.primary_username.username),
            },
            follow_redirects=False,
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior

    assert response.status_code == 400
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).first()
        is None
    )


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_full_body_encryption_fallback_to_generic_when_no_fields(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    for field_def in user.primary_username.message_fields:
        field_def.enabled = False
    db.session.commit()

    sent: list[str] = []

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text
    assert sent == ["You have a new Hush Line message! Please log in to read it."]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.encrypt_message", side_effect=ValueError("boom"))
def test_profile_full_body_encryption_exception_falls_back_to_generic(
    encrypt_message_mock: MagicMock,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = encrypt_message_mock
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    sent: list[str] = []

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "encrypted_email_body": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text
    assert sent == ["You have a new Hush Line message! Please log in to read it."]


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_extra_fields(client: FlaskClient, app: Flask, user: User) -> None:
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    user.primary_username.extra_field_label2 = "Arbitrary Link"
    user.primary_username.extra_field_value2 = "https://scidsg.org/"
    user.primary_username.extra_field_label3 = "xss should fail"
    user.primary_username.extra_field_value3 = "<script>alert('xss')</script>"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    signal_username_span = soup.find("span", class_="extra-field-value")
    assert signal_username_span is not None
    assert signal_username_span.text.strip() == "singleusername.666"

    link = soup.find("a", href="https://scidsg.org/")
    assert link is not None
    assert link.get("target") == "_blank"
    assert "noopener" in link.get("rel", [])
    assert "noreferrer" in link.get("rel", [])

    # Verify that XSS is correctly escaped
    # Search for the XSS string directly in the HTML with both possible escapes
    html_str = str(soup)
    assert (
        "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in html_str
        or "&lt;script&gt;alert('xss')&lt;/script&gt;" in html_str
    )
    assert "<script>alert('xss')</script>" not in html_str


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_account_category_renders_first_extra_field(
    client: FlaskClient, user: User
) -> None:
    user.account_category = AccountCategory.LAWYER.value
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    user.primary_username.extra_field_label2 = "Website"
    user.primary_username.extra_field_value2 = "https://scidsg.org/"
    user.primary_username.extra_field_label3 = "Pronouns"
    user.primary_username.extra_field_value3 = "they/them"
    user.primary_username.extra_field_label4 = "Timezone"
    user.primary_username.extra_field_value4 = "UTC"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    labels = [node.get_text(strip=True) for node in soup.select(".extra-field-label")]
    values = [node.get_text(" ", strip=True) for node in soup.select(".extra-field-value")]
    assert labels == ["Category", "Signal username", "Website", "Pronouns", "Timezone"]
    assert values[0] == "Attorney"


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_location_renders_as_single_extra_field(client: FlaskClient, user: User) -> None:
    user.country = "US"
    user.subdivision = "IL"
    user.city = "Chicago"
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    labels = [node.get_text(strip=True) for node in soup.select(".extra-field-label")]
    values = [node.get_text(" ", strip=True) for node in soup.select(".extra-field-value")]
    assert labels == ["Location", "Signal username"]
    assert values[0] == "Chicago, IL, US"


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_location_keeps_full_names_outside_us(client: FlaskClient, user: User) -> None:
    user.country = "Australia"
    user.subdivision = "New South Wales"
    user.city = "Sydney"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    labels = [node.get_text(strip=True) for node in soup.select(".extra-field-label")]
    values = [node.get_text(" ", strip=True) for node in soup.select(".extra-field-value")]
    assert labels == ["Location"]
    assert values[0] == "Sydney, New South Wales, Australia"


def test_redirect_submit_message_route(client: FlaskClient, user: User) -> None:
    response = client.get(
        url_for("redirect_submit_message", username=user.primary_username.username),
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["Location"].endswith(
        url_for("profile", username=user.primary_username.username)
    )


def test_submission_success_without_reply_slug_redirects_directory(client: FlaskClient) -> None:
    response = client.get(url_for("submission_success"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("directory"))


def test_submission_success_404_when_message_missing(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["reply_slug"] = "does-not-exist"

    response = client.get(url_for("submission_success"), follow_redirects=True)
    assert response.status_code == 404
    assert "404: Not Found" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_submission_success_uses_public_base_url_for_reply_link(app: Flask, user: User) -> None:
    app.config["SERVER_NAME"] = None
    app.config["PUBLIC_BASE_URL"] = "https://safe.example"
    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.commit()

    with app.test_request_context(
        url_for("submission_success"),
        base_url="http://evil.example",
    ):
        from flask import session

        session["reply_slug"] = message.reply_slug
        response = app.view_functions["submission_success"]()

    assert isinstance(response, str)
    assert f'href="https://safe.example/reply/{message.reply_slug}"' in response
    assert "evil.example" not in response
