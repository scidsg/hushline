#!/usr/bin/env python
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app
from sqlalchemy import func, select

from hushline import create_app
from hushline.chat_key_lifecycle import chat_key_fingerprint
from hushline.db import db
from hushline.model import (
    ChatKey,
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    FieldValue,
    Message,
    MessageStatus,
    NotificationRecipient,
    Tier,
    User,
    Username,
)
from hushline.storage import S3Driver, public_store

with open(Path(__file__).parent.parent / "tests" / "test_pgp_key.txt") as f:
    PGP_KEY = f.read()

OVERRIDES_PATH = Path(__file__).parent / "dev_data_overrides.json"


def main() -> None:
    print("Adding dev data")
    with create_app().app_context():
        create_tiers()
        create_users()
        create_org_settings()
        create_sample_messages()
        create_sample_conversations()
        create_localstack_buckets()


def default_users() -> list[dict[str, object]]:
    return [
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
            "is_featured": True,
            "tier": "Super User",
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
            "notification_recipients": [
                {"email": "editor@vandelay.news", "pgp_key": PGP_KEY, "enabled": True},
                {"email": "standards@vandelay.news", "pgp_key": PGP_KEY, "enabled": True},
                {"email": "board@vandelay.news", "pgp_key": PGP_KEY, "enabled": True},
            ],
        },
        {
            "username": "jerryseinfeld",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "is_featured": True,
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
            "is_featured": True,
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
            "is_featured": True,
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
            "is_verified": True,
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
            "is_verified": True,
            "display_name": "Gob Bluth",
            "bio": (
                "I'm an illusionist, not a magician—tricks are what a hooker does for money. "
                "Tip me off to any half-decent gigs or adorable rabbits."
            ),
            "pgp_key": PGP_KEY,
        },
        {
            "username": "busterbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Buster Bluth",
            "bio": (
                "Motherboy champion and proud hook-hand owner. "
                "Use my tip line for anything related to juice boxes or loose seals."
            ),
            "pgp_key": PGP_KEY,
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
            "is_verified": True,
            "display_name": "Tobias Fünke",
            "bio": (
                "Never-nude, aspiring actor, and first analrapist. "
                "Tip me on potential casting calls or discreet cutoffs sales."
            ),
            "pgp_key": PGP_KEY,
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
        {
            "username": "civicdesk",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Civic Desk",
            "bio": (
                "A public-interest reporting desk focused on local accountability, records, "
                "and tips from people who know how institutions really work."
            ),
            "extra_fields": [
                ("Website", "https://civicdesk.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "publicintegritylab",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Public Integrity Lab",
            "bio": (
                "Researchers and editors reviewing public-sector misconduct, contracting, "
                "procurement, and oversight tips."
            ),
            "extra_fields": [
                ("Website", "https://integritylab.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "studentpresswatch",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Student Press Watch",
            "bio": (
                "A student newsroom collective receiving tips about schools, universities, "
                "and campus governance."
            ),
            "extra_fields": [
                ("Website", "https://studentpress.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "laborrightsclinic",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Labor Rights Clinic",
            "bio": (
                "Legal advocates reviewing workplace safety, wage, retaliation, and organizing "
                "concerns from workers."
            ),
            "extra_fields": [
                ("Website", "https://laborrights.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "opensourcewatch",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Open Source Watch",
            "bio": (
                "Software maintainers and security researchers coordinating responsible tips "
                "about digital infrastructure risks."
            ),
            "extra_fields": [
                ("Website", "https://opensourcewatch.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "communitylegalaid",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Community Legal Aid",
            "bio": (
                "Attorneys and advocates available for civil rights, housing, benefits, and "
                "community accountability tips."
            ),
            "extra_fields": [
                ("Website", "https://legalaid.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "climateaccountability",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Climate Accountability Desk",
            "bio": (
                "Reporters investigating environmental compliance, climate risk disclosures, "
                "and public-interest science."
            ),
            "extra_fields": [
                ("Website", "https://climatedesk.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "privacyresearchdesk",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Privacy Research Desk",
            "bio": (
                "Researchers collecting tips about data misuse, surveillance, privacy harms, "
                "and accountability failures."
            ),
            "extra_fields": [
                ("Website", "https://privacyresearch.example", True),
            ],
            "pgp_key": PGP_KEY,
        },
        {
            "username": "georgecostanzakr",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "onboarding_complete": True,
            "display_name": "조지 코스탄자",
            "bio": (
                "부모님 집에 살고 있지만 늘 큰 계획을 세우는 조지 코스탄자입니다. "
                "수축 현상, 밀수된 초콜릿 바, 그리고 수상한 거래에 대한 제보를 보내 주세요."
            ),
        },
    ]


def create_users() -> None:
    users = default_users()
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
        is_featured = cast(bool, data.get("is_featured", False))
        extra_fields = cast(List[Tuple[str, str, bool]], data.get("extra_fields", []))
        pgp_key = cast(Optional[str], data.get("pgp_key"))  # Optional PGP key
        onboarding_complete = cast(bool, data.get("onboarding_complete", True))
        email = cast(Optional[str], data.get("email", f"{username}@hushline.app"))
        tier_name = cast(str, data.get("tier", "Free"))
        notification_recipients = cast(
            list[dict[str, object]], data.get("notification_recipients", [])
        )

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
                is_featured=is_featured,
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

        if tier_name == "Super User":
            user.set_business_tier()
        else:
            user.set_free_tier()

        if notification_recipients:
            user.notification_recipients.clear()
            for position, recipient_data in enumerate(notification_recipients):
                recipient = NotificationRecipient(
                    enabled=cast(bool, recipient_data.get("enabled", True)),
                    position=position,
                )
                recipient.email = cast(Optional[str], recipient_data.get("email"))
                recipient.pgp_key = cast(Optional[str], recipient_data.get("pgp_key"))
                user.notification_recipients.append(recipient)
            user.sync_legacy_notification_email()

        primary.display_name = display_name
        primary.bio = bio
        primary.show_in_directory = True
        primary.is_verified = is_verified
        primary.is_featured = is_featured

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
            "👋 Find lawyers, journalists, and others who support whistleblowers using "
            "the Hush Line directory. An account is not required to send a message. "
            "[Learn more](https://hushline.app)."
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


DOCS_CONVERSATION_PUBLIC_ID = "33333333-3333-4333-8333-333333333333"
DOCS_FOLLOWUP_CONVERSATION_PUBLIC_ID = "33333333-3333-4333-8333-333333333334"
DOCS_SCREENSHOT_PASSWORD = "Test-testtesttesttest-1"  # noqa: S105


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64url_uint(value: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(32, "big")).decode("ascii").rstrip("=")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _jwk_public(private_key: ec.EllipticCurvePrivateKey, *, key_ops: list[str]) -> dict[str, Any]:
    numbers = private_key.public_key().public_numbers()
    return {
        "crv": "P-256",
        "ext": True,
        "key_ops": key_ops,
        "kty": "EC",
        "x": _b64url_uint(numbers.x),
        "y": _b64url_uint(numbers.y),
    }


def _jwk_private(private_key: ec.EllipticCurvePrivateKey, *, key_ops: list[str]) -> dict[str, Any]:
    private_numbers = private_key.private_numbers()
    jwk = _jwk_public(private_key, key_ops=key_ops)
    jwk["d"] = _b64url_uint(private_numbers.private_value)
    return jwk


def _wrap_private_key_bundle(private_key_bundle: dict[str, Any], password: str) -> dict[str, Any]:
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf_iterations = 310000
    kdf_params: dict[str, int | str] = {"iterations": kdf_iterations, "hash": "SHA-256"}
    wrapping_key = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=kdf_iterations,
    ).derive(password.encode("utf-8"))
    encrypted_private_key = AESGCM(wrapping_key).encrypt(
        iv,
        json.dumps(private_key_bundle, separators=(",", ":")).encode("utf-8"),
        None,
    )
    return {
        "encrypted_private_key": json.dumps(
            {
                "algorithm": "AES-GCM",
                "iv": _b64(iv),
                "ciphertext": _b64(encrypted_private_key),
            },
            separators=(",", ":"),
        ),
        "kdf_algorithm": "PBKDF2-SHA-256",
        "kdf_params": kdf_params,
        "kdf_salt": _b64(salt),
        "wrapping_algorithm": "AES-GCM",
    }


def _demo_chat_identity(password: str) -> dict[str, Any]:
    ecdh_private_key = ec.generate_private_key(ec.SECP256R1())
    signing_private_key = ec.generate_private_key(ec.SECP256R1())
    private_key_bundle = {
        "ecdh_private_jwk": _jwk_private(ecdh_private_key, key_ops=["deriveKey"]),
        "signing_private_jwk": _jwk_private(signing_private_key, key_ops=["sign"]),
    }
    public_key = json.dumps(_jwk_public(ecdh_private_key, key_ops=[]), separators=(",", ":"))
    public_signing_key = json.dumps(
        _jwk_public(signing_private_key, key_ops=["verify"]), separators=(",", ":")
    )
    return {
        "ecdh_private_key": ecdh_private_key,
        "signing_private_key": signing_private_key,
        "payload": {
            "public_key": public_key,
            "public_signing_key": public_signing_key,
            **_wrap_private_key_bundle(private_key_bundle, password),
            "recovery_state": None,
        },
    }


def _reset_demo_chat_key(user: User, identity: dict[str, Any]) -> ChatKey:
    for chat_key in list(user.chat_keys):
        db.session.delete(chat_key)
    db.session.flush()
    payload = cast(dict[str, Any], identity["payload"])
    chat_key = ChatKey(
        user=user,
        key_version=1,
        public_key=cast(str, payload["public_key"]),
        public_signing_key=cast(str, payload["public_signing_key"]),
        encrypted_private_key=cast(str, payload["encrypted_private_key"]),
        kdf_algorithm=cast(str, payload["kdf_algorithm"]),
        kdf_params=cast(dict[str, Any], payload["kdf_params"]),
        kdf_salt=cast(str, payload["kdf_salt"]),
        wrapping_algorithm=cast(str, payload["wrapping_algorithm"]),
        recovery_state=None,
    )
    db.session.add(chat_key)
    db.session.flush()
    return chat_key


def _encrypt_conversation_copy(  # noqa: PLR0913
    *,
    plaintext: str,
    conversation: Conversation,
    sender_participant: ConversationParticipant,
    sender_identity: dict[str, Any],
    recipient_participant: ConversationParticipant,
    recipient_identity: dict[str, Any],
) -> str:
    recipient_payload = cast(dict[str, Any], recipient_identity["payload"])
    recipient_public_key = cast(
        ec.EllipticCurvePrivateKey, recipient_identity["ecdh_private_key"]
    ).public_key()
    ephemeral_private_key = ec.generate_private_key(ec.SECP256R1())
    shared_secret = ephemeral_private_key.exchange(ec.ECDH(), recipient_public_key)
    iv = os.urandom(12)
    context = {
        "purpose": "hushline.chat.message",
        "conversation_public_id": conversation.public_id,
        "sender_participant_id": str(sender_participant.id),
        "recipient_participant_id": str(recipient_participant.id),
        "recipient_key_version": 1,
        "recipient_public_key_fingerprint": chat_key_fingerprint(
            cast(str, recipient_payload["public_key"])
        ),
    }
    ciphertext = AESGCM(shared_secret).encrypt(
        iv,
        plaintext.encode("utf-8"),
        _canonical_json(context).encode("utf-8"),
    )
    ephemeral_public_key = json.dumps(
        _jwk_public(ephemeral_private_key, key_ops=[]), separators=(",", ":")
    )
    envelope: dict[str, Any] = {
        "v": 2,
        "algorithm": "ECDH-P256-AES-GCM",
        "ephemeral_public_key": ephemeral_public_key,
        "iv": _b64(iv),
        "ciphertext": _b64(ciphertext),
        "context": context,
    }
    signed_payload = {
        "v": envelope["v"],
        "algorithm": envelope["algorithm"],
        "ephemeral_public_key": envelope["ephemeral_public_key"],
        "iv": envelope["iv"],
        "ciphertext": envelope["ciphertext"],
        "context": envelope["context"],
    }
    signature = cast(ec.EllipticCurvePrivateKey, sender_identity["signing_private_key"]).sign(
        _canonical_json(signed_payload).encode("utf-8"), ec.ECDSA(hashes.SHA256())
    )
    r, s = decode_dss_signature(signature)
    envelope["signature"] = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return json.dumps(envelope, separators=(",", ":"))


def _conversation_plaintext(content: str, created_at: datetime) -> str:
    return json.dumps(
        {
            "content": content,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
        },
        separators=(",", ":"),
    )


def _seed_demo_conversation(
    *,
    public_id: str,
    artvandelay: User,
    newman: User,
    identities: dict[str, dict[str, Any]],
    messages: list[tuple[str, str, datetime]],
) -> None:
    existing = db.session.scalars(
        select(Conversation).where(Conversation.public_id == public_id)
    ).one_or_none()
    if existing is not None:
        db.session.delete(existing)
        db.session.flush()

    conversation = Conversation()
    conversation.public_id = public_id
    artvandelay_participant = ConversationParticipant()
    artvandelay_participant.conversation = conversation
    artvandelay_participant.user = artvandelay
    artvandelay_participant.has_usable_public_key = True
    newman_participant = ConversationParticipant()
    newman_participant.conversation = conversation
    newman_participant.user = newman
    newman_participant.has_usable_public_key = True
    db.session.add(conversation)
    db.session.flush()

    participants = {
        "artvandelay": artvandelay_participant,
        "newman": newman_participant,
    }
    for sender_username, content, created_at in messages:
        sender_participant = participants[sender_username]
        conversation_message = ConversationMessage()
        conversation_message.conversation = conversation
        conversation_message.sender_participant = sender_participant
        conversation_message.created_at = created_at
        db.session.add(conversation_message)
        db.session.flush()

        plaintext = _conversation_plaintext(content, created_at)
        for recipient_username, recipient_participant in participants.items():
            encrypted_copy = ConversationMessageCopy()
            encrypted_copy.recipient_participant = recipient_participant
            encrypted_copy.encrypted_payload = _encrypt_conversation_copy(
                plaintext=plaintext,
                conversation=conversation,
                sender_participant=sender_participant,
                sender_identity=identities[sender_username],
                recipient_participant=recipient_participant,
                recipient_identity=identities[recipient_username],
            )
            conversation_message.encrypted_copies.append(encrypted_copy)

    latest_message = conversation.messages[-1]
    artvandelay_participant.last_read_at = latest_message.created_at
    artvandelay_participant.last_read_message = latest_message


def create_sample_conversations() -> None:
    artvandelay_username = db.session.scalars(
        select(Username).where(
            func.lower(Username._username) == "artvandelay",
            Username.is_primary.is_(True),
        )
    ).one_or_none()
    newman_username = db.session.scalars(
        select(Username).where(
            func.lower(Username._username) == "newman",
            Username.is_primary.is_(True),
        )
    ).one_or_none()
    if artvandelay_username is None or newman_username is None:
        return

    identities = {
        "artvandelay": _demo_chat_identity(DOCS_SCREENSHOT_PASSWORD),
        "newman": _demo_chat_identity(DOCS_SCREENSHOT_PASSWORD),
    }
    _reset_demo_chat_key(artvandelay_username.user, identities["artvandelay"])
    _reset_demo_chat_key(newman_username.user, identities["newman"])

    base_time = datetime(2026, 2, 16, 17, 30, tzinfo=timezone.utc)
    _seed_demo_conversation(
        public_id=DOCS_CONVERSATION_PUBLIC_ID,
        artvandelay=artvandelay_username.user,
        newman=newman_username.user,
        identities=identities,
        messages=[
            (
                "newman",
                'Hello, "Art" ;)',
                base_time,
            ),
            (
                "artvandelay",
                "Hello, Newman.",
                base_time + timedelta(minutes=8),
            ),
            (
                "newman",
                "I think I have information you might find interesting about the Human Fund.",
                base_time + timedelta(minutes=19),
            ),
            (
                "artvandelay",
                "The charity? Please tell me the funds are not just in a coffee can.",
                base_time + timedelta(minutes=24),
            ),
            (
                "newman",
                'Not a coffee can. A very official envelope labeled "miscellaneous grievances."',
                base_time + timedelta(minutes=37),
            ),
        ],
    )
    _seed_demo_conversation(
        public_id=DOCS_FOLLOWUP_CONVERSATION_PUBLIC_ID,
        artvandelay=artvandelay_username.user,
        newman=newman_username.user,
        identities=identities,
        messages=[
            (
                "newman",
                "I found the records-retention note. It says the backup exports run weekly.",
                base_time - timedelta(days=1),
            ),
            (
                "artvandelay",
                "Good. Please do not send files from a work device or managed network.",
                base_time - timedelta(days=1, minutes=-11),
            ),
        ],
    )
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
