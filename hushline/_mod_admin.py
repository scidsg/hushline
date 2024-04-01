#!/usr/bin/env python

import sys

from hushline import create_app
from hushline.db import db
from hushline.model import SecondaryUsername, User


def toggle_admin(username: str) -> None:
    # First, try to find a primary user
    user = User.query.filter_by(primary_username=username).first()

    # If not found, try to find a secondary user
    if not user:
        secondary_username = SecondaryUsername.query.filter_by(username=username).first()
        if secondary_username:
            user = secondary_username.primary_user
        else:
            print("User not found.")
            return

    # Toggle admin status
    user.is_admin = not user.is_admin
    db.session.commit()

    print(f"User {username} admin status toggled to {user.is_admin}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python admin.py <username>")
        sys.exit(1)

    username = sys.argv[1]

    with create_app().app_context():
        toggle_admin(username)
