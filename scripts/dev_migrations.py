#!/usr/bin/env python
from hushline import create_app
from hushline.db import db


def main() -> None:
    print("Creating database tables")
    with create_app().app_context():
        db.create_all()

    print("Database tables created")


if __name__ == "__main__":
    main()
