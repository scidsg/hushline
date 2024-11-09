import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, User, Username


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_message(client: FlaskClient, user: User) -> None:
    # Setup: create primary and alias usernames, and a message for the user
    primary_username = Username(
        user_id=user.id, _username="test", is_primary=True, show_in_directory=True
    )
    db.session.add(primary_username)
    db.session.flush()

    # Create message associated with primary username
    message = Message(id=1, content="Test Message", username_id=primary_username.id)
    db.session.add(message)
    db.session.commit()

    # Ensure message exists before deletion
    assert db.session.query(Message).filter_by(id=1).first() is not None

    # Execute: Call the delete route
    response = client.post(url_for("delete_message", message_id=1), follow_redirects=True)

    # Verify: Confirm message deletion and check response text
    assert response.status_code == 200
    assert "Message deleted successfully" in response.text
    assert db.session.query(Message).filter_by(id=1).first() is None
