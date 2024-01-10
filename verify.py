# python verify.py username

import sys
from app import app, db, User


def toggle_verification(username):
    user = User.query.filter_by(username=username).first()
    if user:
        user.is_verified = not user.is_verified
        db.session.commit()
        print(f"User {username} verification status toggled to {user.is_verified}.")
    else:
        print("User not found.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python toggle_verification.py <username>")
        sys.exit(1)

    username = sys.argv[1]

    # Create an application context
    with app.app_context():
        toggle_verification(username)
