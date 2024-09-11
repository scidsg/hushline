#!/usr/bin/env python

from pprint import pprint

from hushline import create_app
from hushline.db import db
from hushline.model import User


def main() -> None:
    create_app().app_context().push()

    user_args = {
        "username": "test",
        "password": "Test-testtesttesttest-1",
    }

    user = User(**user_args)
    db.session.add(user)
    db.session.commit()

    print("User created:")
    pprint(user_args)


if __name__ == "__main__":
    main()
