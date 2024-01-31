import sys
import argparse
import logging
from app import app, db, User

# Function to toggle verification status
def toggle_verification(username):
    try:
        user = User.query.filter_by(username=username).first()
        if user:
            with db.session.begin():
                user.is_verified = not user.is_verified
            logging.info(f"User '{username}' verification status toggled to {user.is_verified}.")
        else:
            logging.warning(f"User '{username}' not found.")
    except Exception as e:
        logging.error(f"An error occurred while toggling verification status: {e}")
        sys.exit(1)

# Main function to process command line argument
def main(username):
    with app.app_context():
        toggle_verification(username)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Toggle user verification status.')
    parser.add_argument('username', help='Username of the user', type=lambda s: s.strip())
    args = parser.parse_args()

    if not 0 < len(args.username) <= 30:  # Adjust the length constraint as needed
        logging.error("Invalid username length.")
        sys.exit(1)

    main(args.username)
