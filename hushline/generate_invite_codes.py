#!/usr/bin/env python
import secrets
from datetime import datetime, timedelta, timezone

from hushline import create_app
from hushline.db import db
from hushline.model import InviteCode


def create_invite_code() -> str:
    with create_app().app_context():
        # Ensure all tables are created
        db.create_all()

        # Generate a unique invite code
        code = secrets.token_urlsafe(16)

        # Set the expiration date for the invite code to one year from now
        expiration_date = datetime.now(timezone.utc) + timedelta(days=365)

        # Create a new InviteCode object
        new_code = InviteCode(code=code, expiration_date=expiration_date)

        # Add the new code to the session and commit it to the database
        db.session.add(new_code)
        db.session.commit()

        # Return the generated code
        return code


if __name__ == "__main__":
    # Prompt the user to enter the number of invite codes to generate
    number_of_codes = int(input("Enter the number of invite codes to generate: "))

    # Generate and print the specified number of invite codes
    for _ in range(number_of_codes):
        print(create_invite_code())
