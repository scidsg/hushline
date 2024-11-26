from uuid import uuid4

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, MessageStatus, MessageStatusText, User
from hushline.settings.forms import SetMessageStatusTextForm
from tests.helpers import form_to_data


def test_default_replies(client: FlaskClient, user: User, message: Message) -> None:
    # precondition
    assert not db.session.scalars(db.select(MessageStatusText).filter_by(user_id=user.id)).all()

    for status in MessageStatus:
        message.status = status
        db.session.commit()

        resp = client.get(url_for("message_reply", slug=message.reply_slug))
        assert resp.status_code == 200
        assert status.display_str in resp.text
        assert status.default_text in resp.text


def test_custom_replies(client: FlaskClient, user: User, message: Message) -> None:
    for status in MessageStatus:
        text = str(uuid4())
        message.status = status
        msg_status_txt = MessageStatusText(user_id=user.id, status=status, markdown=text)
        db.session.add(msg_status_txt)
        db.session.commit()

        resp = client.get(url_for("message_reply", slug=message.reply_slug))
        assert resp.status_code == 200
        assert status.display_str in resp.text
        assert text in resp.text
        assert status.default_text not in resp.text


@pytest.mark.usefixtures("_authenticated_user")
def test_set_custom_replies(client: FlaskClient, user: User) -> None:
    text = str(uuid4())
    status = MessageStatus.PENDING
    resp = client.post(
        url_for("settings.replies"),
        data=form_to_data(SetMessageStatusTextForm(data={"status": status.value, "markdown": text})),
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
    resp = client.get(url_for("message", id=message.id))
    assert resp.status_code == 200
    assert "Message" in resp.text


@pytest.mark.usefixtures("_authenticated_user")
def test_message_page_wrong_user(
    client: FlaskClient, user: User, user2: User, message2: Message
) -> None:
    resp = client.get(url_for("message", id=message2.id), follow_redirects=True)
    assert resp.status_code == 200
    assert "Message" not in resp.text
    assert "That page doesn&#39;t exist" in resp.text, resp.text
