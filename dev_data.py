#!/usr/bin/env python
from hushline import create_app
from hushline.db import db
from hushline.model import User, Username


def main() -> None:
    create_app().app_context().push()

    username = "test"
    password = "Test-testtesttesttest-1"  # noqa: S105

    user = User(password=password)
    db.session.add(user)
    db.session.flush()

    un1 = Username(user_id=user.id, _username=username, is_primary=True, show_in_directory=True)
    un2 = Username(
        user_id=user.id, _username=username + "-alias", is_primary=False, show_in_directory=True
    )
    db.session.add(un1)
    db.session.add(un2)
    db.session.commit()

    print(f"User created:\n  username = {username}\n  password = {password}")


if __name__ == "__main__":
    main()
