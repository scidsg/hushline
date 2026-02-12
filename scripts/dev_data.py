#!/usr/bin/env python
import json
from pathlib import Path
from typing import List, Optional, Tuple, cast

from flask import current_app
from sqlalchemy import func, select

from hushline import create_app
from hushline.db import db
from hushline.model import FieldValue, Message, MessageStatus, Tier, User, Username
from hushline.storage import S3Driver, public_store

with open(Path(__file__).parent.parent / "tests" / "test_pgp_key.txt") as f:
    PGP_KEY = f.read()

OVERRIDES_PATH = Path(__file__).parent / "dev_data_overrides.json"


def main() -> None:
    print("Adding dev data")
    with create_app().app_context():
        create_users()
        create_org_settings()
        create_sample_messages()
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
            "bio": (
                "Message for account verification, technical problems, and general feedback!"
                "If we receive a message about a crime that is occurring or about to occur it "
                "will be forwarded to law enforcement."
            ),
            "extra_fields": [
                ("Website", "https://hushline.app", True),
                ("Signal", "@hushline.1337", False),
            ],
            "pgp_key": PGP_KEY,
            "onboarding_complete": True,
            "email": "admin@hushline.app",
        },
        {
            "username": "artvandelay",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Art Vandelay",
            "bio": (
                "Art Vandelay is an award-winning investigative reporter covering marine biology, "
                "architecture, and sports, with bylines in The Vandelay Herald. Demo account."
            ),
            "extra_fields": [
                ("Website", "https://vandelay.news", True),
                ("Signal", "@artvandelay.01", False),
            ],
            "pgp_key": PGP_KEY,
            "onboarding_complete": True,
            "email": "artvandelay@hushline.app",
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
            "is_verified": False,
            "display_name": "",
            # Keep newman as an intentionally incomplete account for onboarding screenshots.
            "onboarding_complete": False,
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
    users = apply_user_overrides(users)

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
        onboarding_complete = cast(bool, data.get("onboarding_complete", True))
        email = cast(Optional[str], data.get("email", f"{username}@hushline.app"))

        primary = db.session.scalars(
            select(Username).where(
                func.lower(Username._username) == username.lower(), Username.is_primary.is_(True)
            )
        ).one_or_none()

        if primary is None:
            # Create a new user
            user = User(password=password, is_admin=is_admin)
            db.session.add(user)
            db.session.flush()

            primary = Username(
                user_id=user.id,
                _username=username,
                display_name=display_name,
                bio=bio,
                is_primary=True,
                show_in_directory=True,
                is_verified=is_verified,
            )
            db.session.add(primary)

            alias = Username(
                user_id=user.id,
                _username=f"{username}-alias",
                display_name=f"{display_name} (Alias)",
                bio=f"{bio} (Alias)",
                is_primary=False,
                show_in_directory=True,
                is_verified=False,
            )
            db.session.add(alias)
            created = True
        else:
            user = primary.user
            created = False

        # Keep fixtures deterministic across repeated runs.
        user.is_admin = is_admin
        user.password_hash = password
        user.pgp_key = pgp_key
        user.onboarding_complete = onboarding_complete
        if onboarding_complete and pgp_key and email:
            user.enable_email_notifications = True
            user.email_include_message_content = True
            user.email_encrypt_entire_body = True
            user.email = email
        else:
            user.enable_email_notifications = False
            user.email_include_message_content = False
            user.email_encrypt_entire_body = False
            user.email = None

        primary.display_name = display_name
        primary.bio = bio
        primary.show_in_directory = True
        primary.is_verified = is_verified

        for i in range(1, MAX_EXTRA_FIELDS + 1):
            setattr(primary, f"extra_field_label{i}", None)
            setattr(primary, f"extra_field_value{i}", None)
            setattr(primary, f"extra_field_verified{i}", False)
        for i, (label, value, verified) in enumerate(extra_fields, start=1):
            if i > MAX_EXTRA_FIELDS:
                break
            setattr(primary, f"extra_field_label{i}", label)
            setattr(primary, f"extra_field_value{i}", value)
            setattr(primary, f"extra_field_verified{i}", verified)

        db.session.commit()
        primary.create_default_field_defs()

        if created:
            print(f"Test user created:\n  username = {username}")
        else:
            print(f"User updated:\n  username = {username}")


def apply_user_overrides(users: list[dict[str, object]]) -> list[dict[str, object]]:
    if not OVERRIDES_PATH.exists():
        return users

    try:
        content = json.loads(OVERRIDES_PATH.read_text())
    except json.JSONDecodeError:
        print(f"Skipping invalid overrides file: {OVERRIDES_PATH}")
        return users

    if not isinstance(content, dict):
        print(f"Skipping invalid overrides file shape: {OVERRIDES_PATH}")
        return users

    by_username = content.get("users", {})
    if not isinstance(by_username, dict):
        print(f"Skipping invalid overrides users key in: {OVERRIDES_PATH}")
        return users

    updated: list[dict[str, object]] = []
    for user in users:
        uname = cast(str, user.get("username", ""))
        override = by_username.get(uname, {})
        if isinstance(override, dict):
            merged = dict(user)
            merged.update(override)
            updated.append(merged)
        else:
            updated.append(user)

    print(f"Applied dev data overrides from {OVERRIDES_PATH}")
    return updated


def create_org_settings() -> None:
    from hushline.model import OrganizationSetting

    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, False)
    OrganizationSetting.upsert(
        OrganizationSetting.DIRECTORY_INTRO_TEXT,
        (
            "👋 Find lawyers, journalists, and others who support whistleblowers using the "
            "Hush Line User Directory. An account is not required to send a message."
        ),
    )
    OrganizationSetting.upsert(OrganizationSetting.GUIDANCE_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.GUIDANCE_EXIT_BUTTON_TEXT, "Leave")
    OrganizationSetting.upsert(
        OrganizationSetting.GUIDANCE_EXIT_BUTTON_LINK, "https://www.wikipedia.org/"
    )
    OrganizationSetting.upsert(
        OrganizationSetting.GUIDANCE_PROMPTS,
        [
            {
                "heading_text": "Before you submit",
                "prompt_text": "Use a personal device and network whenever possible.",
                "index": 0,
            },
            {
                "heading_text": "Protect your identity",
                "prompt_text": "Avoid sharing names, locations, or metadata that can identify you.",
                "index": 1,
            },
            {
                "heading_text": "Need more privacy?",
                "prompt_text": "Use Tor Browser for stronger anonymity before sending a message.",
                "index": 2,
            },
        ],
    )
    db.session.commit()


def create_sample_messages() -> None:
    samples = []

    admin_status_counts = [
        (MessageStatus.ACCEPTED, 10),
        (MessageStatus.DECLINED, 5),
        (MessageStatus.ARCHIVED, 3),
        (MessageStatus.PENDING, 2),
    ]
    admin_idx = 1
    for status, count in admin_status_counts:
        for _ in range(count):
            samples.append(
                {
                    "owner": "admin",
                    "public_id": f"11111111-1111-1111-1111-{admin_idx:012d}",
                    "reply_slug": f"sample-reply-admin-{admin_idx:03d}",
                    "status": status.value,
                    "field_text": (
                        f"Admin sample message {admin_idx} for {status.display_str.lower()} "
                        "inbox screenshots."
                    ),
                }
            )
            admin_idx += 1

    samples.extend(
        [
            {
                "owner": "artvandelay",
                "public_id": "22222222-2222-2222-2222-222222222222",
                "reply_slug": "sample-reply-artvandelay",
                "status": "PENDING",
                "field_text": "Sample message for Art Vandelay status and reply screenshots.",
            },
            {
                "owner": "artvandelay",
                "public_id": "22222222-2222-2222-2222-222222222223",
                "reply_slug": "sample-reply-artvandelay-accepted",
                "status": "ACCEPTED",
                "field_text": "Art Vandelay example message that appears under accepted.",
            },
            {
                "owner": "artvandelay",
                "public_id": "22222222-2222-2222-2222-222222222224",
                "reply_slug": "sample-reply-artvandelay-declined",
                "status": "DECLINED",
                "field_text": "Art Vandelay example message for declined workflow screenshots.",
            },
        ]
    )

    for item in samples:
        owner = db.session.scalars(
            select(Username).where(
                func.lower(Username._username) == cast(str, item["owner"]).lower(),
                Username.is_primary.is_(True),
            )
        ).one_or_none()
        if owner is None:
            continue

        msg = db.session.scalars(
            select(Message).where(Message.public_id == cast(str, item["public_id"]))
        ).one_or_none()
        if msg is None:
            msg = Message(username_id=owner.id)
            msg.public_id = cast(str, item["public_id"])
            msg.reply_slug = cast(str, item["reply_slug"])
            db.session.add(msg)
            db.session.flush()

            field_def = owner.message_fields[0]
            fv = FieldValue(
                field_definition=field_def,
                message=msg,
                value=cast(str, item["field_text"]),
                encrypted=field_def.encrypted,
            )
            db.session.add(fv)
        else:
            msg.reply_slug = cast(str, item["reply_slug"])

        msg.status = MessageStatus[cast(str, item["status"]).upper()]

        db.session.commit()


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
