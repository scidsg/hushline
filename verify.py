# python verify.py username

import sys
from app import app, db, User, SecondaryUser


def toggle_verification(username):
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

    # Toggle verification status
    user.is_verified = not user.is_verified
    db.session.commit()

    print(f"User {username} verification status toggled to {user.is_verified}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify.py <username>")
        sys.exit(1)

    username = sys.argv[1]

    with app.app_context():
        toggle_verification(username)
