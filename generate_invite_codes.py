#!/usr/bin/env python
from hushline import create_app
from hushline.db import db
from hushline.model import InviteCode


def create_invite_code() -> str:
    with create_app().app_context():
        # Ensure all tables are created
        db.create_all()

        # Create a new InviteCode object
        new_code = InviteCode()
        db.session.add(new_code)
        db.session.commit()

        # Return the generated code
        return new_code.code


if __name__ == "__main__":
    # Prompt the user to enter the number of invite codes to generate
    number_of_codes = int(input("Enter the number of invite codes to generate: "))

    # Generate and print the specified number of invite codes
    for _ in range(number_of_codes):
        print(create_invite_code())
