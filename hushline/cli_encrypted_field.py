from dataclasses import dataclass

import click
from alembic.runtime.migration import MigrationContext
from cryptography.fernet import InvalidToken
from flask import Flask
from flask.cli import AppGroup
from sqlalchemy import inspect
from sqlalchemy.exc import NoSuchTableError

from hushline.crypto import (
    ENCRYPTED_FIELD_CONTRACTS,
    ENCRYPTED_FIELD_ENVELOPE_PREFIX,
    ENCRYPTED_FIELD_LEGACY_MAX_LENGTH,
    decrypt_field,
)
from hushline.db import db


@dataclass(frozen=True)
class EncryptedFieldCapacityReport:
    contract_id: str
    table: str
    column: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class EncryptedFieldCiphertextReport:
    contract_id: str
    table: str
    column: str
    legacy_fernet: int
    envelope_fernet: int
    null_empty: int
    malformed: int
    decrypt_failures: int

    @property
    def decryptable(self) -> bool:
        return self.decrypt_failures == 0


def _current_alembic_revision() -> str:
    context = MigrationContext.configure(db.session.connection())
    heads = context.get_current_heads()
    return ", ".join(heads) if heads else "not stamped"


def _encrypted_field_column_capacity_reports() -> list[EncryptedFieldCapacityReport]:
    inspector = inspect(db.engine)
    reports: list[EncryptedFieldCapacityReport] = []
    for contract in ENCRYPTED_FIELD_CONTRACTS:
        try:
            columns = inspector.get_columns(contract.table)
        except NoSuchTableError:
            reports.append(
                EncryptedFieldCapacityReport(
                    contract_id=contract.id,
                    table=contract.table,
                    column=contract.column,
                    ready=False,
                    detail="missing table",
                )
            )
            continue

        matching_column = next(
            (candidate for candidate in columns if candidate["name"] == contract.column),
            None,
        )
        if matching_column is None:
            reports.append(
                EncryptedFieldCapacityReport(
                    contract_id=contract.id,
                    table=contract.table,
                    column=contract.column,
                    ready=False,
                    detail="missing column",
                )
            )
            continue

        length = getattr(matching_column["type"], "length", None)
        ready = length is None or length > ENCRYPTED_FIELD_LEGACY_MAX_LENGTH
        detail = "unbounded" if length is None else f"length {length}"
        reports.append(
            EncryptedFieldCapacityReport(
                contract_id=contract.id,
                table=contract.table,
                column=contract.column,
                ready=ready,
                detail=detail,
            )
        )

    return reports


def _classify_encrypted_field_values() -> list[EncryptedFieldCiphertextReport]:
    inspector = inspect(db.engine)
    reports: list[EncryptedFieldCiphertextReport] = []
    for contract in ENCRYPTED_FIELD_CONTRACTS:
        try:
            columns = inspector.get_columns(contract.table)
        except NoSuchTableError:
            continue
        if not any(candidate["name"] == contract.column for candidate in columns):
            continue

        table = db.metadata.tables.get(contract.table)
        if table is None or contract.column not in table.c:
            continue
        column = table.c[contract.column]
        legacy_fernet = 0
        envelope_fernet = 0
        null_empty = 0
        malformed = 0
        decrypt_failures = 0

        for value in db.session.execute(db.select(column).select_from(table)).scalars():
            if value is None or value == "":
                null_empty += 1
                continue

            if not isinstance(value, str):
                malformed += 1
                decrypt_failures += 1
                continue

            try:
                decrypt_field(value)
            except InvalidToken:
                malformed += 1
                decrypt_failures += 1
                continue
            except (UnicodeDecodeError, ValueError):
                decrypt_failures += 1
                continue

            if value.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX):
                envelope_fernet += 1
            else:
                legacy_fernet += 1

        reports.append(
            EncryptedFieldCiphertextReport(
                contract_id=contract.id,
                table=contract.table,
                column=contract.column,
                legacy_fernet=legacy_fernet,
                envelope_fernet=envelope_fernet,
                null_empty=null_empty,
                malformed=malformed,
                decrypt_failures=decrypt_failures,
            )
        )

    return reports


def register_encrypted_field_commands(app: Flask) -> None:
    encrypted_field_cli = AppGroup(
        "encrypted-field",
        help="Encrypted-field migration and rollout commands",
    )

    @encrypted_field_cli.command("preflight")
    def preflight() -> None:
        """Report encrypted-field envelope rollout readiness without mutating data."""
        capacity_reports = _encrypted_field_column_capacity_reports()
        ciphertext_reports = _classify_encrypted_field_values()

        click.echo(f"Current Alembic revision: {_current_alembic_revision()}")
        click.echo("Storage column capacity:")
        for report in capacity_reports:
            click.echo(
                "- "
                f"{report.contract_id} ({report.table}.{report.column}): "
                f"{'ready' if report.ready else 'blocked'} ({report.detail})"
            )

        click.echo("Ciphertext readiness:")
        for ciphertext_report in ciphertext_reports:
            click.echo(
                "- "
                f"{ciphertext_report.contract_id} "
                f"({ciphertext_report.table}.{ciphertext_report.column}): "
                f"legacy Fernet: {ciphertext_report.legacy_fernet}; "
                f"envelope Fernet: {ciphertext_report.envelope_fernet}; "
                f"null/empty: {ciphertext_report.null_empty}; "
                f"malformed: {ciphertext_report.malformed}; "
                f"decryptable: {'yes' if ciphertext_report.decryptable else 'no'}"
            )

        blocked_capacity = [report.contract_id for report in capacity_reports if not report.ready]
        malformed_reports = [
            report.contract_id for report in ciphertext_reports if report.malformed
        ]
        decrypt_failure_reports = [
            report.contract_id for report in ciphertext_reports if not report.decryptable
        ]
        if blocked_capacity or malformed_reports or decrypt_failure_reports:
            reasons = []
            if blocked_capacity:
                reasons.append("schema is not envelope-ready")
            if malformed_reports:
                reasons.append("malformed ciphertext values are present")
            if decrypt_failure_reports:
                reasons.append("one or more non-empty values failed decryptability checks")
            raise click.ClickException(
                "Encrypted-field preflight readiness: blocked (" + "; ".join(reasons) + ")"
            )

        click.echo("Encrypted-field preflight readiness: ready")

    app.cli.add_command(encrypted_field_cli)
