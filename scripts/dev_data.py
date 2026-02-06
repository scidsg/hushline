#!/usr/bin/env python
from pathlib import Path
from typing import List, Optional, Tuple, cast

from flask import current_app
from sqlalchemy import func
from sqlalchemy.sql import exists

from hushline import create_app
from hushline.db import db
from hushline.model import Tier, User, Username
from hushline.storage import S3Driver, public_store

with open(Path(__file__).parent.parent / "tests" / "test_pgp_key.txt") as f:
    PGP_KEY = f.read()


def main() -> None:
    print("Adding dev data")
    with create_app().app_context():
        create_users()
        create_tiers()
        create_localstack_buckets()


def create_users() -> None:
    users = [
        {
            "username": "admin",
            "password": "Test-testtesttesttest-1",
            "is_admin": True,
            "is_verified": True,
            "display_name": "Hush Line Admin",
            "bio": "Hush Line administrator account.",
            "pgp_key": PGP_KEY,
        },
        {
            "username": "artvandelay",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Art Vandelay",
            "bio": (
                "Art is the CEO of Vandelay Industries, an international "
                "importing/exporting company. Potato and corn chips, "
                "diapers, and matches."
            ),
        },
        {
            "username": "jerryseinfeld",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Jerry Seinfeld",
            "bio": (
                "I'm a neurotic stand-up comic who loves cereal and Superman. "
                "Use my tip line to rant about nothing—it's a show about nothing!"
            ),
            "extra_fields": [
                ("Website", "https://jerryseinfeld.com", True),
                ("Signal", "@Jerry.01", False),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "georgecostanza",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "George Costanza",
            "bio": (
                "Perpetually unemployed, living with my parents, but I have "
                "big plans. Use my tip line if you spot shrinkage or contraband Twix."
            ),
            "extra_fields": [
                ("Website", "https://yankees.com", False),
                ("Signal", "@George.99", False),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "elainebenes",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Elaine Benes",
            "bio": (
                "I dance like nobody’s watching—because they shouldn’t. "
                "Send tips on questionable sponges."
            ),
            "extra_fields": [
                ("Email", "elaine@pendant.com", False),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "cosmokramer",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Cosmo Kramer",
            "bio": (
                "I'm the wacky neighbor with grand schemes (pizza bagels, anyone?). "
                "Hit my tip line if you discover the next big invention idea."
            ),
            "extra_fields": [
                ("Business Ideas", "Homemade Pizzeria", False),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "newman",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Postal Employee Newman",
            "bio": "Postal worker and sworn enemy to Jerry. Hello, Jerry.",
            "pgp_key": PGP_KEY,
        },
        {
            "username": "frankcostanza",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Frank Costanza",
            "bio": (
                "I invented the manzier and celebrate Festivus. "
                "Tip line for any beef you got—SERENITY NOW!"
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "michaelbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Michael Bluth",
            "bio": (
                "Holding this family together with hopes, dreams, and bad magic shows. "
                "Use my tip line to warn me if Gob’s illusions go too far."
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "gobbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Gob Bluth",
            "bio": (
                "I'm an illusionist, not a magician—tricks are what a hooker does for money. "
                "Tip me off to any half-decent gigs or adorable rabbits."
            ),
        },
        {
            "username": "busterbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Buster Bluth",
            "bio": (
                "Motherboy champion and proud hook-hand owner. "
                "Use my tip line for anything related to juice boxes or loose seals."
            ),
        },
        {
            "username": "lucillebluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Lucille Bluth",
            "bio": (
                "Manipulative matriarch with a taste for vodka. "
                "Notify me about 2-for-1 martini deals."
            ),
            "extra_fields": [
                ("Favorite Drink", "Vodka Martini", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "tobiasfunke",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Tobias Fünke",
            "bio": (
                "Never-nude, aspiring actor, and first analrapist. "
                "Tip me on potential casting calls or discreet cutoffs sales."
            ),
        },
        {
            "username": "larrydavid",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Larry David",
            "bio": (
                "I’m just trying to say what everyone’s thinking—sometimes it’s trouble. "
                "Use my tip line for petty gripes or leftover 'spite store' leads."
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "jeffgreene",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Jeff Greene",
            "bio": (
                "Larry’s longtime manager, often enabling awkward situations. "
                "Send me tips on hush-hush deals or who’s offended Larry this week."
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "leonblack",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Leon Black",
            "bio": (
                "I mooch off Larry and offer streetwise pep talks. "
                "Hit me with tips on side hustles or a new 'shit bow' story."
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "dwightschrute",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Dwight Schrute",
            "bio": (
                "Assistant to the Regional Manager. "
                "Contact my tip line for beet sales or suspicious behavior from Jim."
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "martymcfly",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Marty McFly",
            "bio": (
                "Time-traveling teen with a hoverboard. "
                "Use my tip line if someone calls me chicken or there's a DeLorean sighting."
            ),
            "pgp_key": PGP_KEY,
        },
    ]

    MAX_EXTRA_FIELDS = 4

    for data in users:
        # Extract and cast basic user information
        username = cast(str, data["username"])
        password = cast(str, data["password"])
        is_admin = cast(bool, data["is_admin"])
        display_name = cast(str, data.get("display_name", username))
        bio = cast(str, data.get("bio", ""))[:250]  # Ensure truncation to 250 characters
        is_verified = cast(bool, data.get("is_verified", False))
        extra_fields = cast(List[Tuple[str, str, bool]], data.get("extra_fields", []))
        pgp_key = cast(Optional[str], data.get("pgp_key"))  # Optional PGP key

        # Check if user already exists
        if not db.session.query(
            exists().where(func.lower(Username._username) == username.lower())
        ).scalar():
            # Create a new user
            user = User(password=password, is_admin=is_admin)

            # Assign PGP key if provided
            if pgp_key:
                user.pgp_key = pgp_key

            db.session.add(user)
            db.session.flush()

            # Create primary username
            un1 = Username(
                user_id=user.id,
                _username=username,
                display_name=display_name,
                bio=bio,
                is_primary=True,
                show_in_directory=True,
                is_verified=is_verified,
            )

            # Create alias username
            un2 = Username(
                user_id=user.id,
                _username=f"{username}-alias",
                display_name=f"{display_name} (Alias)",
                bio=f"{bio} (Alias)",
                is_primary=False,
                show_in_directory=True,
                is_verified=False,
            )

            # Assign extra fields to the primary username
            for i, (label, value, verified) in enumerate(extra_fields, start=1):
                if i > MAX_EXTRA_FIELDS:
                    break  # Stop if maximum number of extra fields is exceeded
                setattr(un1, f"extra_field_label{i}", label)
                setattr(un1, f"extra_field_value{i}", value)
                setattr(un1, f"extra_field_verified{i}", verified)

            # Add the new usernames to the database
            db.session.add(un1)
            db.session.add(un2)
            db.session.commit()

            print(f"Test user created:\n  username = {username}\n  password = {password}")
        else:
            print(f"User already exists: {username}")


def create_tiers() -> None:
    tiers = [
        {
            "name": "Free",
            "monthly_amount": 0,
        },
        {
            "name": "Super User",
            "monthly_amount": 500,
        },
    ]
    for data in tiers:
        name = cast(str, data["name"])
        monthly_amount = cast(int, data["monthly_amount"])
        if not db.session.scalar(db.exists(Tier).where(Tier.name == name).select()):
            tier = Tier(name, monthly_amount)
            db.session.add(tier)
            db.session.commit()

        print(f"Tier:\n  name = {name}\n  monthly_amount = {monthly_amount}")

    print("Dev data added")


def create_localstack_buckets() -> None:
    driver = public_store._driver
    if isinstance(driver, S3Driver):
        bucket = current_app.config[driver._config_name("S3_BUCKET")]
        driver._client.create_bucket(Bucket=bucket)
        print(f"Public storage bucket: {bucket}")


if __name__ == "__main__":
    main()
