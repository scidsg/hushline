#!/usr/bin/env python

import sys

from sqlalchemy import func

from hushline import create_app
from hushline.db import db
from hushline.models import Username


def toggle_admin(username: str) -> None:
    uname = db.session.scalars(
        db.select(Username).where(func.lower(Username._username) == username.lower())
    ).one_or_none()
    if not uname:
        print("User not found.")
        return

    uname.user.is_admin = not uname.user.is_admin
    db.session.commit()

    print(f"User {username} admin status toggled to {uname.user.is_admin}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:  # noqa: PLR2004
        print("Usage: python make_admin.py <username>")
        sys.exit(1)

    with create_app().app_context():
        toggle_admin(sys.argv[1])
