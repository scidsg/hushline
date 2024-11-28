#!/usr/bin/env python
from typing import cast

from flask import current_app
from sqlalchemy.sql import exists

from hushline import create_app
from hushline.db import db
from hushline.model import Tier, User, Username
from hushline.storage import S3Driver, public_store


def main() -> None:
    print("Adding dev data")
    create_app().app_context().push()
    create_users()
    create_tiers()
    create_localstack_buckets()


def create_users() -> None:
    users = [
        {
            "username": "test",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
        },
        {
            "username": "admin",
            "password": "Test-testtesttesttest-1",
            "is_admin": True,
        },
    ]

    for data in users:
        username = data["username"]
        if not db.session.query(exists(Username).where(Username._username == username)).scalar():
            user = User(password=data["password"], is_admin=data["is_admin"])
            db.session.add(user)
            db.session.flush()

            un1 = Username(
                user_id=user.id,
                _username=data["username"],  # type: ignore
                is_primary=True,
                show_in_directory=True,
                is_verified=True,
            )
            un2 = Username(
                user_id=user.id,
                _username=data["username"] + "-alias",  # type: ignore
                is_primary=False,
                show_in_directory=True,
                is_verified=False,
            )
            db.session.add(un1)
            db.session.add(un2)
            db.session.commit()

        print(f"Test user:\n  username = {data['username']}\n  password = {data['password']}")


def create_tiers() -> None:
    tiers = [
        {
            "name": "Free",
            "monthly_amount": 0,
        },
        {
            "name": "Business",
            "monthly_amount": 2000,
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
