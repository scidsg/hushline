import sys
from your_app_module import db, User  # Replace 'your_app_module' with the actual name


def toggle_verification(username):
    user = User.query.filter_by(username=username).first()
    if user:
        user.is_verified = not user.is_verified
        db.session.commit()
        print(f"User {username} verification status toggled.")
    else:
        print("User not found.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python toggle_verification.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    toggle_verification(username)
