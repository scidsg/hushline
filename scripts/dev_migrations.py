#!/usr/bin/env python
from hushline import create_app
from hushline.db import db


def main() -> None:
    with create_app().app_context():
        db.create_all()


if __name__ == "__main__":
    main()
