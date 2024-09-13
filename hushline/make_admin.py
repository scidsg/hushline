#!/usr/bin/env python

import sys

from hushline import create_app
from hushline.db import db
from hushline.model import User


def toggle_admin(username: str) -> None:
    user = User.query.filter_by(primary_username=username).one_or_none()
    if not user:
        print("User not found.")
        return

    # Toggle admin status
    user.is_admin = not user.is_admin
    db.session.commit()

    print(f"User {username} admin status toggled to {user.is_admin}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:  # noqa: PLR2004
        print("Usage: python make_admin.py <username>")
        sys.exit(1)

    username = sys.argv[1]

    with create_app().app_context():
        toggle_admin(username)
