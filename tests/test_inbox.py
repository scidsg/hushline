import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import FieldValue, Message, MessageStatus, User, Username


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_delete_own_message(client: FlaskClient, user: User) -> None:
    # Create a message for the authenticated user
    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    for field_def in user.primary_username.message_fields:
        field_value = FieldValue(
            field_def,
            message,
            "test_value",
            field_def.encrypted,
        )
        db.session.add(field_value)
        db.session.commit()

    # Attempt to delete the user's own message
    response = client.post(
        url_for("delete_message", public_id=message.public_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message deleted successfully" in response.text
    assert db.session.get(Message, message.id) is None  # Ensure message was deleted


@pytest.mark.usefixtures("_authenticated_user")
def test_cannot_delete_other_user_message(
    client: FlaskClient, user: User, user_password: str
) -> None:
    # Create another user within the test
    other_user = User(password=user_password)
    db.session.add(other_user)
    db.session.flush()

    other_username = Username(user_id=other_user.id, _username="otheruser", is_primary=True)
    db.session.add(other_username)
    db.session.commit()

    # Create a message for the other user
    other_user_message = Message(username_id=other_username.id)
    db.session.add(other_user_message)
    db.session.commit()

    for field_def in other_username.message_fields:
        field_value = FieldValue(
            field_def,
            other_user_message,
            "test_value",
            field_def.encrypted,
        )
        db.session.add(field_value)
        db.session.commit()

    # Attempt to delete the other user's message
    response = client.post(
        url_for("delete_message", public_id=other_user_message.public_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message not found" in response.text
    assert (
        db.session.get(Message, other_user_message.id) is not None
    )  # Ensure message was not deleted


@pytest.mark.usefixtures("_authenticated_user")
def test_filter_on_status(client: FlaskClient, user: User, user_alias: Username) -> None:
    messages = []
    for status in MessageStatus:
        message = Message(username_id=user.primary_username.id)
        message.status = status
        db.session.add(message)
        db.session.flush()
        messages.append(message)

        for field_def in user.primary_username.message_fields:
            field_def.encrypted = False

        for field_def in user.primary_username.message_fields:
            field_value = FieldValue(
                field_def,
                message,
                "test_value",
                field_def.encrypted,
            )
            db.session.add(field_value)
            db.session.flush()
    db.session.commit()

    # no filter
    resp = client.get(url_for("inbox"))
    for msg in messages:
        assert resp.status_code == 200
        assert f'href="{url_for("message", public_id=msg.public_id)}"' in resp.text

    # status filter
    for msg in messages:
        resp = client.get(url_for("inbox", status=msg.status.value))

        # find match
        assert resp.status_code == 200
        assert f'href="{url_for("message", public_id=msg.public_id)}"' in resp.text

        # don't find the other matches
        for other_msg in messages:
            if other_msg.public_id != msg.public_id:
                assert (
                    f'href="{url_for("message", public_id=other_msg.public_id)}"' not in resp.text
                )


@pytest.mark.usefixtures("_authenticated_user")
def test_inbox_invalid_status_returns_bad_request(client: FlaskClient) -> None:
    response = client.get(url_for("inbox", status="not-a-status"), follow_redirects=False)
    assert response.status_code == 400


def test_inbox_missing_user_row_returns_404(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
        sess["user_id"] = 999999
        sess["username"] = "ghost"

    response = client.get(url_for("inbox"), follow_redirects=False)
    assert response.status_code == 404
