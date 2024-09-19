#!/usr/bin/env python
from sqlalchemy.sql import exists

from hushline import create_app
from hushline.db import db
from hushline.model import User, Username


def main() -> None:
    create_app().app_context().push()

    users = [
        {
            "username": "test",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
        },
        {
            "username": "admin",
            "password": "Test-testtesttesttest-1",
            "is_admin": True,
        },
    ]

    for data in users:
        username = data["username"]
        if not db.session.query(exists(Username).where(Username._username == username)).scalar():
            user = User(password=data["password"], is_admin=data["is_admin"])
            db.session.add(user)
            db.session.flush()

            un1 = Username(
                user_id=user.id,
                _username=data["username"],  # type: ignore
                is_primary=True,
                show_in_directory=True,
            )
            un2 = Username(
                user_id=user.id,
                _username=data["username"] + "-alias",  # type: ignore
                is_primary=False,
                show_in_directory=True,
            )
            db.session.add(un1)
            db.session.add(un2)
            db.session.commit()

        print(f"Test user:\n  username = {data['username']}\n  password = {data['password']}")


if __name__ == "__main__":
    main()
