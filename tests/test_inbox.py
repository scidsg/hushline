import os

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, User, Username

# Define test passwords
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "TestPassword123!")
OTHER_USER_PASSWORD = os.getenv("OTHER_USER_PASSWORD", "OtherUserPass456!")


@pytest.fixture()
def setup_user_data(user: User) -> None:
    """Fixture to create primary and alias usernames and a message for the authenticated user."""
    primary_username = Username(
        user_id=user.id,
        _username="primary_user",
        is_primary=True,
        show_in_directory=True,
    )
    alias_username = Username(
        user_id=user.id,
        _username="primary_user_alias",
        is_primary=False,
        show_in_directory=True,
    )
    db.session.add_all([primary_username, alias_username])
    db.session.flush()

    message = Message(
        username_id=primary_username.id,
        content="Test message for deletion.",
    )
    db.session.add(message)
    db.session.commit()

    return primary_username, alias_username, message


@pytest.fixture()
def other_user() -> User:
    """Fixture to create another user for testing cross-user access."""
    other_user = User(password=OTHER_USER_PASSWORD, is_admin=False)
    db.session.add(other_user)
    db.session.flush()

    other_username = Username(
        user_id=other_user.id,
        _username="other_user",
        is_primary=True,
        show_in_directory=True,
    )
    db.session.add(other_username)
    db.session.flush()

    other_message = Message(
        username_id=other_username.id,
        content="Other user's message.",
    )
    db.session.add(other_message)
    db.session.commit()

    return other_user, other_message


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_message(client: FlaskClient, user: User, setup_user_data, other_user) -> None:
    primary_username, alias_username, message = setup_user_data
    other_user, other_message = other_user

    # Test deletion of authenticated user's own message
    response = client.post(
        url_for("delete_message", message_id=message.id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message deleted successfully" in response.text

    # Verify that the message is removed from the database
    assert db.session.get(Message, message.id) is None

    # Test that User A (authenticated user) cannot delete User B's (other_user's) message
    response = client.post(
        url_for("delete_message", message_id=other_message.id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message not found" in response.text

    # Verify that the other user's message still exists
    assert db.session.get(Message, other_message.id) is not None
