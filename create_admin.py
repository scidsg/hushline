# python create_admin.py myusername

from app import app, db, User


def make_admin(username):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user:
            # Set the user as admin
            # user.is_admin = True  # Assuming you have an is_admin attribute or similar
            db.session.commit()
            print(f"User {username} is now an admin.")
        else:
            print(f"User {username} not found.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python create_admin.py <username>")
    else:
        username = sys.argv[1]
        make_admin(username)
