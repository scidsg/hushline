#!/usr/bin/env python

import sys

from hushline import SecondaryUser, User, app, db


def toggle_admin(username):
    # First, try to find a primary user
    user = User.query.filter_by(primary_username=username).first()

    # If not found, try to find a secondary user
    if not user:
        secondary_user = SecondaryUser.query.filter_by(username=username).first()
        if secondary_user:
            user = secondary_user.primary_user
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

    with app.app_context():
        toggle_admin(username)
