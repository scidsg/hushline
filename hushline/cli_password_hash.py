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


def _legacy_passlib_scrypt_row_count() -> int:
    legacy_row_count = db.session.scalar(
        db.select(db.func.count(User.id)).where(
            User._password_hash.like(f"{LEGACY_PASSLIB_SCRYPT_PREFIX}%")
        )
    )
    return legacy_row_count or 0


def _evaluate_passlib_removal_gate(
    *,
    legacy_row_count: int,
    legacy_verification_successes: int,
    reviewed_in_repo_legacy_verifier: bool,
) -> tuple[bool, str]:
    if reviewed_in_repo_legacy_verifier:
        return True, "reviewed in-repo legacy verifier declared"

    if legacy_row_count != 0:
        return False, "legacy passlib scrypt rows remain"

    if legacy_verification_successes != 0:
        return False, "measured legacy verification success volume is non-zero"

    return True, "legacy rows and measured legacy verification success volume are both zero"


def _emit_passlib_compatibility_notes() -> None:
    click.echo(
        "Current build verification support: passlib $scrypt$ and native prefix-based hashes."
    )
    click.echo(
        "Rollback note: builds before passlib removal can verify both legacy $scrypt$ and native "
        "prefix-based hashes."
    )


def register_password_hash_commands(app: Flask) -> None:
    password_hash_cli = AppGroup("password-hash", help="Password hash migration commands")

    @password_hash_cli.command("report")
    @click.option(
        "--legacy-verification-successes",
        type=click.IntRange(min=0),
        help="Measured legacy passlib verification successes for the release window under review.",
    )
    @click.option(
        "--reviewed-in-repo-legacy-verifier",
        is_flag=True,
        default=False,
        help="Use the reviewed in-repo legacy verifier path instead of requiring zero legacy rows.",
    )
    def report(
        legacy_verification_successes: int | None,
        reviewed_in_repo_legacy_verifier: bool,
    ) -> None:
        """Report legacy password-hash migration status."""
        legacy_row_count = _legacy_passlib_scrypt_row_count()

        click.echo(f"Legacy passlib scrypt rows: {legacy_row_count}")
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
        _emit_passlib_compatibility_notes()

        if legacy_verification_successes is None:
            click.echo(
                "Measured legacy verification successes: provide "
                "--legacy-verification-successes <count> before making a removal decision."
            )
            click.echo("Passlib removal readiness: blocked")
            return

        click.echo(f"Measured legacy verification successes: {legacy_verification_successes}")
        gate_ready, gate_reason = _evaluate_passlib_removal_gate(
            legacy_row_count=legacy_row_count,
            legacy_verification_successes=legacy_verification_successes,
            reviewed_in_repo_legacy_verifier=reviewed_in_repo_legacy_verifier,
        )
        click.echo(
            "Legacy verifier path: "
            + (
                "reviewed_in_repo_legacy_verifier"
                if reviewed_in_repo_legacy_verifier
                else "passlib_dependency"
            )
        )
        click.echo(f"Passlib removal readiness: {'ready' if gate_ready else 'blocked'}")
        click.echo(f"Passlib removal reason: {gate_reason}")

    @password_hash_cli.command("can-remove-passlib")
    @click.option(
        "--legacy-verification-successes",
        type=click.IntRange(min=0),
        required=True,
        help="Measured legacy passlib verification successes for the release window under review.",
    )
    @click.option(
        "--reviewed-in-repo-legacy-verifier",
        is_flag=True,
        default=False,
        help=(
            "Allow removal based on a reviewed in-repo legacy verifier instead of zero "
            "legacy rows."
        ),
    )
    def can_remove_passlib(
        legacy_verification_successes: int,
        reviewed_in_repo_legacy_verifier: bool,
    ) -> None:
        """Exit successfully only when the passlib removal gate is satisfied."""
        legacy_row_count = _legacy_passlib_scrypt_row_count()
        gate_ready, gate_reason = _evaluate_passlib_removal_gate(
            legacy_row_count=legacy_row_count,
            legacy_verification_successes=legacy_verification_successes,
            reviewed_in_repo_legacy_verifier=reviewed_in_repo_legacy_verifier,
        )

        click.echo(f"Legacy passlib scrypt rows: {legacy_row_count}")
        click.echo(f"Measured legacy verification successes: {legacy_verification_successes}")
        click.echo(
            "Legacy verifier path: "
            + (
                "reviewed_in_repo_legacy_verifier"
                if reviewed_in_repo_legacy_verifier
                else "passlib_dependency"
            )
        )
        _emit_passlib_compatibility_notes()
        if gate_ready:
            click.echo("Passlib removal readiness: ready")
            return

        raise click.ClickException(f"Passlib removal readiness: blocked ({gate_reason})")

    app.cli.add_command(password_hash_cli)
