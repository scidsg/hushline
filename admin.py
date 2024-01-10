# python toggle_admin.py username

import sys
from app import app, db, User


def toggle_admin(username):
    user = User.query.filter_by(username=username).first()
    if user:
        user.is_admin = not user.is_admin
        db.session.commit()
        print(f"User {username} admin status toggled to {user.is_admin}.")
    else:
        print("User not found.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python toggle_admin.py <username>")
        sys.exit(1)

    username = sys.argv[1]

    # Create an application context
    with app.app_context():
        toggle_admin(username)
