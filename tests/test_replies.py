from uuid import uuid4

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, MessageStatus, MessageStatusText, User
from hushline.settings.forms import SetMessageStatusTextForm
from tests.helpers import form_to_data


def test_message_reply_404_for_unknown_slug(client: FlaskClient) -> None:
    resp = client.get(url_for("message_reply", slug="does-not-exist"), follow_redirects=True)
    assert resp.status_code == 404
    assert "404: Not Found" in resp.text


def test_default_replies(client: FlaskClient, user: User, message: Message) -> None:
    # precondition
    assert not db.session.scalars(db.select(MessageStatusText).filter_by(user_id=user.id)).all()

    for status in MessageStatus:
        message.status = status
        db.session.commit()

        resp = client.get(url_for("message_reply", slug=message.reply_slug))
        assert resp.status_code == 200
        assert (status.emoji + " " + status.display_str) in resp.text
        assert status.default_text in resp.text


def test_custom_replies(client: FlaskClient, user: User, message: Message) -> None:
    for status in MessageStatus:
        text = str(uuid4())
        message.status = status
        msg_status_txt = MessageStatusText(
            user_id=user.id,  # type: ignore[call-arg]
            status=status,  # type: ignore[call-arg]
            markdown=text,  # type: ignore[call-arg]
        )
        db.session.add(msg_status_txt)
        db.session.commit()

        resp = client.get(url_for("message_reply", slug=message.reply_slug))
        assert resp.status_code == 200
        assert (status.emoji + " " + status.display_str) in resp.text
        assert text in resp.text
        assert status.default_text not in resp.text


@pytest.mark.usefixtures("_authenticated_user")
def test_set_custom_replies(client: FlaskClient, user: User) -> None:
    # Make the user an admin for this test
    db.session.commit()

    text = str(uuid4())
    status = MessageStatus.PENDING
    resp = client.post(
        url_for("settings.replies"),
        data=form_to_data(
            SetMessageStatusTextForm(data={"status": status.value, "markdown": text})
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Reply text set" in resp.text

    msg_status_text = db.session.scalars(
        db.select(MessageStatusText).filter_by(user_id=user.id, status=status)
    ).one()
    assert msg_status_text.markdown == text


@pytest.mark.usefixtures("_authenticated_user")
def test_message_page(client: FlaskClient, user: User, message: Message) -> None:
    resp = client.get(url_for("message", public_id=message.public_id))
    assert resp.status_code == 200
    assert "Message" in resp.text


@pytest.mark.usefixtures("_authenticated_user")
def test_message_page_wrong_user(
    client: FlaskClient, user: User, user2: User, message2: Message
) -> None:
    resp = client.get(url_for("message", public_id=message2.public_id), follow_redirects=True)
    assert resp.status_code == 404
    assert "Message" not in resp.text
    assert "404: Not Found" in resp.text


@pytest.mark.usefixtures("_authenticated_user")
def test_set_message_status_success(client: FlaskClient, message: Message) -> None:
    response = client.post(
        url_for("set_message_status", public_id=message.public_id),
        data={"status": MessageStatus.PENDING.name},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message status updated" in response.text
    db.session.refresh(message)
    assert message.status == MessageStatus.PENDING
    assert message.status_changed_at is not None


@pytest.mark.usefixtures("_authenticated_user")
def test_set_message_status_invalid_form(client: FlaskClient, message: Message) -> None:
    response = client.post(
        url_for("set_message_status", public_id=message.public_id),
        data={},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid status" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_set_message_status_message_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("set_message_status", public_id="missing-public-id"),
        data={"status": MessageStatus.PENDING.name},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("message", public_id="missing-public-id"))


@pytest.mark.usefixtures("_authenticated_user")
def test_set_message_status_multiple_rows_guard(
    client: FlaskClient, message: Message, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Result:
        rowcount = 2

    monkeypatch.setattr("hushline.routes.message.db.session.execute", lambda *_a, **_k: _Result())

    response = client.post(
        url_for("set_message_status", public_id=message.public_id),
        data={"status": MessageStatus.PENDING.name},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Internal server error. Message not updated." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_replies_invalid_form_returns_400(client: FlaskClient, app: Flask) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post(url_for("settings.replies"), data={}, follow_redirects=False)
    assert response.status_code == 400
