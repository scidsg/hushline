import string
import random
import re


def generate_complex_password(length=32):
    if length < 4:  # Ensure length is sufficient to meet all requirements
        raise ValueError("Password length must be at least 4 characters.")

    # Define character sets
    uppercase_letters = string.ascii_uppercase
    lowercase_letters = string.ascii_lowercase
    digits = string.digits
    special_characters = string.punctuation

    # Ensure the password contains at least one of each required character type
    password = [
        random.choice(uppercase_letters),
        random.choice(lowercase_letters),
        random.choice(digits),
        random.choice(special_characters),
    ]

    # Fill the rest of the password length with a random selection of all characters
    all_characters = uppercase_letters + lowercase_letters + digits + special_characters
    password += random.choices(all_characters, k=length - 4)

    # Shuffle to avoid predictable structure
    random.shuffle(password)

    return "".join(password)


# Generate a password that meets the policy
admin_password = generate_complex_password(32)

# Output the generated password
print(admin_password)
