import os
import subprocess


def run_command(command):
    try:
        subprocess.run(command, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")


def main():
    # Initialize the migration environment
    run_command("flask db init")

    # Get custom message for the migration
    migration_message = input("Enter a message for the migration: ")

    # Create a migration script
    run_command(f'flask db migrate -m "{migration_message}"')

    # Apply the migration to the database
    run_command("flask db upgrade")


if __name__ == "__main__":
    main()
