import sys
import logging
from app import app, db, User

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def make_admin(username):
    """Promotes a user to admin status based on their username."""
    with app.app_context():
        # Ensure the username corresponds to a user in the database
        user = User.query.filter_by(primary_username=username).first()
        if user:
            # Check if the user is already an admin
            if user.is_admin:
                logging.info(f"User '{username}' is already an admin.")
            else:
                # Update the user's status to admin
                user.is_admin = True
                try:
                    # Commit changes to the database
                    db.session.commit()
                    logging.info(f"User '{username}' has been granted admin status.")
                except Exception as e:
                    # Log any errors that occur during the database transaction
                    logging.error(f"An error occurred while updating user '{username}': {e}")
        else:
            # Inform the user if the specified username does not exist
            logging.warning(f"No user found with the username '{username}'.")

if __name__ == "__main__":
    # Check that a username has been provided as a command-line argument
    if len(sys.argv) != 2:
        logging.error("Usage: python create_admin.py <username>")
        sys.exit(1)  # Exit with an error status due to incorrect usage

    username = sys.argv[1].strip()  # Remove potential leading/trailing whitespace
    make_admin(username)
