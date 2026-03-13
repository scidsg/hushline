import click
from flask import Flask
from flask.cli import AppGroup

from hushline.db import db
from hushline.model import User
from hushline.password_hasher import (
    LEGACY_PASSLIB_SCRYPT_PREFIX,
    PASSWORD_HASH_REHASH_ON_AUTH_FAILURE_COUNTER,
    PASSWORD_HASH_REHASH_ON_AUTH_SUCCESS_COUNTER,
    PASSWORD_HASH_VERIFICATION_SUCCESS_COUNTER,
)


def register_password_hash_commands(app: Flask) -> None:
    password_hash_cli = AppGroup("password-hash", help="Password hash migration commands")

    @password_hash_cli.command("report")
    def report() -> None:
        """Report legacy password-hash migration status."""
        legacy_row_count = db.session.scalar(
            db.select(db.func.count(User.id)).where(
                User._password_hash.like(f"{LEGACY_PASSLIB_SCRYPT_PREFIX}%")
            )
        )
        legacy_row_count_value = legacy_row_count or 0

        click.echo(f"Legacy passlib scrypt rows: {legacy_row_count_value}")
        click.echo(
            "Legacy verification success counter: "
            f"{PASSWORD_HASH_VERIFICATION_SUCCESS_COUNTER} hash_format=passlib_scrypt"
        )
        click.echo(
            "Rehash-on-auth counters: "
            f"{PASSWORD_HASH_REHASH_ON_AUTH_SUCCESS_COUNTER}, "
            f"{PASSWORD_HASH_REHASH_ON_AUTH_FAILURE_COUNTER}"
        )
        click.echo(
            "Passlib removal gate: legacy rows must stay at 0 for one full release cycle, "
            "and "
            f"{PASSWORD_HASH_VERIFICATION_SUCCESS_COUNTER} "
            "hash_format=passlib_scrypt must stay at 0 "
            "during the same window."
        )

    app.cli.add_command(password_hash_cli)
