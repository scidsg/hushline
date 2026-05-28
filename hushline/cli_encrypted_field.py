import base64
import binascii
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from alembic.runtime.migration import MigrationContext
from cryptography.fernet import InvalidToken
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import inspect
from sqlalchemy.exc import NoSuchTableError

from hushline.config import (
    ENCRYPTED_FIELD_WRITE_FORMAT,
    ConfigParseError,
    EncryptedFieldWriteFormat,
)
from hushline.crypto import (
    ENCRYPTED_FIELD_CONTRACTS,
    ENCRYPTED_FIELD_ENVELOPE_PREFIX,
    ENCRYPTED_FIELD_LEGACY_MAX_LENGTH,
    EncryptedFieldContract,
    EncryptedFieldSchemaNotReadyError,
    build_encrypted_field_aad,
    decrypt_field,
    encrypt_field,
    parse_encrypted_field_aead_envelope,
    parse_encrypted_field_envelope,
)
from hushline.db import db

ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION = "encrypted-field-migration-v1"
ENCRYPTED_FIELD_MIGRATION_TARGET_FORMAT = EncryptedFieldWriteFormat.ENVELOPE_FERNET
ENCRYPTED_FIELD_PREFLIGHT_SCHEMA_REVISION = 1
ENCRYPTED_FIELD_CONTRACT_SET_VERSION = "encrypted-field-contracts-v1"
ENCRYPTED_FIELD_PRODUCTION_GATE_MANIFEST_TYPE = "encrypted-field-production-release-gate"
ENCRYPTED_FIELD_PRODUCTION_GATE_MANIFEST_VERSION = 1


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
    row_count: int
    scanned_rows: int
    legacy_fernet: int
    envelope_fernet: int
    envelope_aes_gcm: int
    null_empty: int
    malformed: int
    decrypt_failures: int

    @property
    def decryptable(self) -> bool:
        return self.decrypt_failures == 0


@dataclass
class EncryptedFieldCiphertextCounts:
    row_count: int = 0
    scanned_rows: int = 0
    legacy_fernet: int = 0
    envelope_fernet: int = 0
    envelope_aes_gcm: int = 0
    null_empty: int = 0
    malformed: int = 0
    decrypt_failures: int = 0


@dataclass(frozen=True)
class EncryptedFieldMigrationFailure:
    contract_id: str
    primary_key: int | None
    phase: str
    error_class: str
    source_left_unchanged: bool = True

    def safe_message(self) -> str:
        pk = "unknown" if self.primary_key is None else str(self.primary_key)
        unchanged = "yes" if self.source_left_unchanged else "unknown"
        return (
            f"contract={self.contract_id} primary_key={pk} phase={self.phase} "
            f"error={self.error_class} source_left_unchanged={unchanged}"
        )


@dataclass
class EncryptedFieldMigrationContractReport:
    contract_id: str
    table: str
    column: str
    examined_rows: int = 0
    eligible_rows: int = 0
    would_migrate_rows: int = 0
    migrated_rows: int = 0
    already_migrated_rows: int = 0
    skipped_rows: int = 0
    decrypt_failures: int = 0
    verification_failures: int = 0
    update_failures: int = 0
    last_processed_primary_key: int | None = None
    remaining_rows: int = 0


@dataclass(frozen=True)
class EncryptedFieldMigrationResumeState:
    helper_version: str
    target_format: str
    batch_size: int
    contract_ids: tuple[str, ...]
    contract_id: str
    last_primary_key: int


class EncryptedFieldMigrationError(RuntimeError):
    def __init__(self, failure: EncryptedFieldMigrationFailure) -> None:
        super().__init__(failure.safe_message())
        self.failure = failure


def _current_alembic_revision() -> str:
    context = MigrationContext.configure(db.session.connection())
    heads = context.get_current_heads()
    return ", ".join(heads) if heads else "not stamped"


def _encrypted_field_column_capacity_reports(
    contracts: tuple[EncryptedFieldContract, ...] | None = None,
) -> list[EncryptedFieldCapacityReport]:
    inspector = inspect(db.engine)
    reports: list[EncryptedFieldCapacityReport] = []
    for contract in contracts or tuple(ENCRYPTED_FIELD_CONTRACTS):
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


def _encoded_json(data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decoded_json(token: str) -> dict[str, Any]:
    try:
        payload = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        data = json.loads(payload.decode())
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise click.ClickException("Invalid encrypted-field migration resume token") from exc
    if not isinstance(data, dict):
        raise click.ClickException("Invalid encrypted-field migration resume token")
    return data


def _serialize_resume_state(state: EncryptedFieldMigrationResumeState) -> str:
    return _encoded_json(
        {
            "batch_size": state.batch_size,
            "contract_id": state.contract_id,
            "contract_ids": list(state.contract_ids),
            "helper_version": state.helper_version,
            "last_primary_key": state.last_primary_key,
            "target_format": state.target_format,
        }
    )


def _parse_resume_state(
    token: str,
    *,
    batch_size: int,
    contract_ids: tuple[str, ...],
    target_format: EncryptedFieldWriteFormat,
) -> EncryptedFieldMigrationResumeState:
    data = _decoded_json(token)
    try:
        state = EncryptedFieldMigrationResumeState(
            helper_version=str(data.get("helper_version", "")),
            target_format=str(data.get("target_format", "")),
            batch_size=int(data.get("batch_size", 0)),
            contract_ids=tuple(data.get("contract_ids", ())),
            contract_id=str(data.get("contract_id", "")),
            last_primary_key=int(data.get("last_primary_key", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise click.ClickException("Invalid encrypted-field migration resume token") from exc
    expected_target = target_format.value
    if state.helper_version != ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION:
        raise click.ClickException("Resume token helper version does not match this helper")
    if state.target_format != expected_target:
        raise click.ClickException("Resume token target format does not match this run")
    if state.batch_size != batch_size:
        raise click.ClickException("Resume token batch size does not match this run")
    if state.contract_ids != contract_ids:
        raise click.ClickException("Resume token contract set does not match this run")
    if state.contract_id not in contract_ids:
        raise click.ClickException("Resume token contract is not in this run")
    if state.last_primary_key < 1:
        raise click.ClickException("Resume token last primary key is invalid")
    return state


def _contract_by_id(contract_id: str) -> EncryptedFieldContract:
    for contract in ENCRYPTED_FIELD_CONTRACTS:
        if contract.id == contract_id:
            return contract
    raise click.ClickException(f"Unknown encrypted-field contract: {contract_id}")


def _selected_contracts(contract_ids: tuple[str, ...]) -> tuple[EncryptedFieldContract, ...]:
    if not contract_ids:
        return tuple(ENCRYPTED_FIELD_CONTRACTS)
    return tuple(_contract_by_id(contract_id) for contract_id in contract_ids)


def _table_for_contract(contract: EncryptedFieldContract) -> Any:
    table = db.metadata.tables.get(contract.table)
    if table is None or "id" not in table.c or contract.column not in table.c:
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=None,
                phase="schema",
                error_class="ContractMismatch",
            )
        )
    return table


def _aad_values_for_row(contract: EncryptedFieldContract, row: Any) -> dict[str, int]:
    values: dict[str, int] = {}
    for aad_field in contract.aad_fields:
        if (
            aad_field == "user_id"
            and contract.table == "users"
            or aad_field == "notification_recipient_id"
            or aad_field == "field_value_id"
        ):
            value = row["id"]
        elif aad_field in row:
            value = row[aad_field]
        else:
            raise EncryptedFieldMigrationError(
                EncryptedFieldMigrationFailure(
                    contract_id=contract.id,
                    primary_key=row.get("id", None),
                    phase="contract",
                    error_class="MissingAADField",
                )
            )
        values[aad_field] = value
    build_encrypted_field_aad(contract, values)
    return values


def _classify_migration_value(value: Any) -> str:
    if value is None or value == "":
        return "null_empty"
    if not isinstance(value, str):
        return "malformed"
    if value.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX):
        return _classify_envelope_value(value)
    return "legacy_fernet"


def _classify_envelope_value(value: str) -> str:
    try:
        parse_encrypted_field_envelope(value)
    except InvalidToken as fernet_error:
        try:
            parse_encrypted_field_aead_envelope(value)
        except InvalidToken as aead_error:
            raise fernet_error from aead_error
        return "envelope_aes_gcm"
    return "envelope_fernet"


@contextmanager
def _target_write_format(format_: EncryptedFieldWriteFormat) -> Any:
    previous = current_app.config.get(ENCRYPTED_FIELD_WRITE_FORMAT)
    current_app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = format_
    try:
        yield
    finally:
        current_app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = previous


def _build_target_ciphertext(
    plaintext: str,
    target_format: EncryptedFieldWriteFormat,
) -> str:
    with _target_write_format(target_format):
        ciphertext = encrypt_field(plaintext)
    if not isinstance(ciphertext, str):
        raise ValueError("Target encrypted-field writer returned an empty value")
    return ciphertext


def _remaining_legacy_rows(contract: EncryptedFieldContract) -> int:
    table = _table_for_contract(contract)
    column = table.c[contract.column]
    count = db.session.scalar(
        db.select(db.func.count())
        .select_from(table)
        .where(column.is_not(None))
        .where(column != "")
        .where(column.not_like(f"{ENCRYPTED_FIELD_ENVELOPE_PREFIX}%"))
    )
    return int(count or 0)


def _verify_ciphertext_plaintext(
    *,
    contract: EncryptedFieldContract,
    primary_key: int,
    phase: str,
    ciphertext: str,
    expected_plaintext: str,
) -> None:
    try:
        plaintext = decrypt_field(ciphertext)
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase=phase,
                error_class=exc.__class__.__name__,
            )
        ) from exc
    if plaintext != expected_plaintext:
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase=phase,
                error_class="PlaintextMismatch",
            )
        )


def _preflight_scan_columns(contract: EncryptedFieldContract, table: Any) -> list[Any]:
    columns = [table.c.id, table.c[contract.column]]
    selected = {"id", contract.column}
    for aad_field in contract.aad_fields:
        if (
            aad_field == "user_id"
            and contract.table == "users"
            or aad_field == "notification_recipient_id"
            or aad_field == "field_value_id"
        ):
            continue
        if aad_field in table.c and aad_field not in selected:
            columns.append(table.c[aad_field])
            selected.add(aad_field)
    return columns


def _process_migration_row(
    *,
    contract: EncryptedFieldContract,
    row: Any,
    dry_run: bool,
    target_format: EncryptedFieldWriteFormat,
    report: EncryptedFieldMigrationContractReport,
) -> bool:
    table = _table_for_contract(contract)
    column = table.c[contract.column]
    primary_key = row["id"]
    value = row[contract.column]
    report.examined_rows += 1
    report.last_processed_primary_key = primary_key

    try:
        classification = _classify_migration_value(value)
    except InvalidToken as exc:
        report.decrypt_failures += 1
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase="classify",
                error_class=exc.__class__.__name__,
            )
        ) from exc

    if classification == "null_empty":
        report.skipped_rows += 1
        return False
    if classification == "malformed":
        report.decrypt_failures += 1
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase="classify",
                error_class="MalformedCiphertext",
            )
        )

    if not isinstance(value, str):
        raise AssertionError("Encrypted-field value classification allowed a non-string")

    aad_values = _aad_values_for_row(contract, row)
    if classification == "envelope_aes_gcm":
        try:
            decrypt_field(value, contract=contract, aad_values=aad_values)
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            report.decrypt_failures += 1
            raise EncryptedFieldMigrationError(
                EncryptedFieldMigrationFailure(
                    contract_id=contract.id,
                    primary_key=primary_key,
                    phase="decrypt",
                    error_class=exc.__class__.__name__,
                )
            ) from exc
        report.already_migrated_rows += 1
        return False

    try:
        plaintext = decrypt_field(value)
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        report.decrypt_failures += 1
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase="decrypt",
                error_class=exc.__class__.__name__,
            )
        ) from exc

    if plaintext is None:
        report.skipped_rows += 1
        return False

    if classification == "envelope_fernet":
        report.already_migrated_rows += 1
        _verify_ciphertext_plaintext(
            contract=contract,
            primary_key=primary_key,
            phase="verify-existing-target",
            ciphertext=value,
            expected_plaintext=plaintext,
        )
        return False

    report.eligible_rows += 1
    try:
        replacement = _build_target_ciphertext(plaintext, target_format)
        if _classify_migration_value(replacement) != "envelope_fernet":
            raise ValueError("Unexpected target encrypted-field format")
        _verify_ciphertext_plaintext(
            contract=contract,
            primary_key=primary_key,
            phase="verify-candidate",
            ciphertext=replacement,
            expected_plaintext=plaintext,
        )
    except (
        EncryptedFieldMigrationError,
        EncryptedFieldSchemaNotReadyError,
        InvalidToken,
        ValueError,
    ) as exc:
        report.verification_failures += 1
        if isinstance(exc, EncryptedFieldMigrationError):
            raise
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase="verify-candidate",
                error_class=exc.__class__.__name__,
            )
        ) from exc

    if dry_run:
        report.would_migrate_rows += 1
        return True

    result = db.session.execute(
        db.update(table)
        .where(table.c.id == primary_key)
        .where(column == value)
        .values({contract.column: replacement})
    )
    if result.rowcount != 1:
        report.update_failures += 1
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase="update",
                error_class="UnexpectedRowCount",
            )
        )

    db.session.flush()
    stored_value = db.session.scalar(db.select(column).where(table.c.id == primary_key))
    if not isinstance(stored_value, str):
        report.verification_failures += 1
        raise EncryptedFieldMigrationError(
            EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=primary_key,
                phase="verify-post-write",
                error_class="MissingStoredCiphertext",
            )
        )
    _verify_ciphertext_plaintext(
        contract=contract,
        primary_key=primary_key,
        phase="verify-post-write",
        ciphertext=stored_value,
        expected_plaintext=plaintext,
    )
    report.migrated_rows += 1
    return True


def _run_encrypted_field_migration_batch(  # noqa: PLR0913
    *,
    contracts: tuple[EncryptedFieldContract, ...],
    dry_run: bool,
    batch_size: int,
    resume_state: EncryptedFieldMigrationResumeState | None,
    full_scan: bool,
    target_format: EncryptedFieldWriteFormat,
) -> tuple[list[EncryptedFieldMigrationContractReport], EncryptedFieldMigrationResumeState | None]:
    capacity_reports = _encrypted_field_column_capacity_reports()
    blocked_capacity = [report for report in capacity_reports if not report.ready]
    if blocked_capacity:
        blocked_ids = ", ".join(report.contract_id for report in blocked_capacity)
        raise click.ClickException(
            f"Encrypted-field migration blocked: schema not ready ({blocked_ids})"
        )
    reports = [
        EncryptedFieldMigrationContractReport(
            contract_id=contract.id,
            table=contract.table,
            column=contract.column,
        )
        for contract in contracts
    ]
    report_by_contract_id = {report.contract_id: report for report in reports}
    processed_rows = 0
    last_state: EncryptedFieldMigrationResumeState | None = None
    started = resume_state is None or full_scan
    contract_ids = tuple(contract.id for contract in contracts)

    for contract in contracts:
        table = _table_for_contract(contract)
        if not started:
            started = contract.id == resume_state.contract_id if resume_state else True
        if not started:
            continue

        start_after = 0
        if not full_scan and resume_state is not None and contract.id == resume_state.contract_id:
            start_after = resume_state.last_primary_key

        rows = db.session.execute(
            db.select(table)
            .where(table.c.id > start_after)
            .order_by(table.c.id.asc())
            .limit(batch_size - processed_rows)
        ).mappings()
        report = report_by_contract_id[contract.id]
        for row in rows:
            if processed_rows >= batch_size:
                break
            _process_migration_row(
                contract=contract,
                row=row,
                dry_run=dry_run,
                target_format=target_format,
                report=report,
            )
            processed_rows += 1
            last_state = EncryptedFieldMigrationResumeState(
                helper_version=ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
                target_format=target_format.value,
                batch_size=batch_size,
                contract_ids=contract_ids,
                contract_id=contract.id,
                last_primary_key=row["id"],
            )
        if processed_rows >= batch_size:
            break

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    for contract in contracts:
        report_by_contract_id[contract.id].remaining_rows = _remaining_legacy_rows(contract)

    remaining_rows = sum(report.remaining_rows for report in reports)
    if processed_rows < batch_size or remaining_rows == 0:
        last_state = None
    return reports, last_state


def _print_migration_reports(  # noqa: PLR0913
    *,
    reports: list[EncryptedFieldMigrationContractReport],
    dry_run: bool,
    batch_size: int,
    target_format: EncryptedFieldWriteFormat,
    next_resume_state: EncryptedFieldMigrationResumeState | None,
    elapsed_seconds: float,
) -> None:
    click.echo(f"Helper version: {ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION}")
    click.echo(f"Mode: {'dry-run' if dry_run else 'live'}")
    click.echo(f"Target format: {target_format.value}")
    click.echo(f"Batch size: {batch_size}")
    click.echo(f"Elapsed seconds: {elapsed_seconds:.3f}")
    for report in reports:
        last_pk = (
            "none"
            if report.last_processed_primary_key is None
            else str(report.last_processed_primary_key)
        )
        status = "complete" if report.remaining_rows == 0 else "pending"
        click.echo(
            "- "
            f"{report.contract_id} ({report.table}.{report.column}): "
            f"status: {status}; "
            f"examined: {report.examined_rows}; "
            f"eligible: {report.eligible_rows}; "
            f"would migrate: {report.would_migrate_rows}; "
            f"migrated: {report.migrated_rows}; "
            f"already migrated: {report.already_migrated_rows}; "
            f"skipped: {report.skipped_rows}; "
            f"decrypt failures: {report.decrypt_failures}; "
            f"verification failures: {report.verification_failures}; "
            f"update failures: {report.update_failures}; "
            f"remaining rows: {report.remaining_rows}; "
            f"last processed primary key: {last_pk}"
        )
    if next_resume_state is None:
        click.echo("Next resume token: complete")
    else:
        click.echo(f"Next resume token: {_serialize_resume_state(next_resume_state)}")


def _classify_preflight_value(
    value: Any,
    *,
    contract: EncryptedFieldContract | None = None,
    aad_values: dict[str, int] | None = None,
) -> str:
    if value is None or value == "":
        return "null_empty"
    if not isinstance(value, str):
        return "malformed"

    is_envelope = value.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    classification = "legacy_fernet"
    if is_envelope:
        try:
            classification = _classify_envelope_value(value)
        except InvalidToken:
            return "malformed"
        if classification == "envelope_aes_gcm":
            if contract is None or aad_values is None:
                return classification
            try:
                decrypt_field(value, contract=contract, aad_values=aad_values)
            except (InvalidToken, UnicodeDecodeError, ValueError):
                return "decrypt_failure"
            return classification

    try:
        decrypt_field(value)
    except InvalidToken:
        return "decrypt_failure" if is_envelope else "malformed"
    except (UnicodeDecodeError, ValueError):
        return "decrypt_failure"

    return classification


def _record_preflight_classification(
    counts: EncryptedFieldCiphertextCounts,
    classification: str,
) -> None:
    counts.row_count += 1
    counts.scanned_rows += 1
    if classification == "null_empty":
        counts.null_empty += 1
    elif classification == "malformed":
        counts.malformed += 1
        counts.decrypt_failures += 1
    elif classification == "decrypt_failure":
        counts.decrypt_failures += 1
    elif classification == "envelope_fernet":
        counts.envelope_fernet += 1
    elif classification == "envelope_aes_gcm":
        counts.envelope_aes_gcm += 1
    else:
        counts.legacy_fernet += 1


def _classify_encrypted_field_values(
    *,
    contracts: tuple[EncryptedFieldContract, ...],
    batch_size: int,
) -> list[EncryptedFieldCiphertextReport]:
    inspector = inspect(db.engine)
    reports: list[EncryptedFieldCiphertextReport] = []
    for contract in contracts:
        try:
            columns = inspector.get_columns(contract.table)
        except NoSuchTableError:
            continue
        if not any(candidate["name"] == contract.column for candidate in columns):
            continue

        table = db.metadata.tables.get(contract.table)
        if table is None or contract.column not in table.c:
            continue
        counts = EncryptedFieldCiphertextCounts()
        last_primary_key = 0

        while True:
            rows = (
                db.session.execute(
                    db.select(*_preflight_scan_columns(contract, table))
                    .select_from(table)
                    .where(table.c.id > last_primary_key)
                    .order_by(table.c.id.asc())
                    .limit(batch_size)
                )
                .mappings()
                .all()
            )
            if not rows:
                break

            for row in rows:
                last_primary_key = row["id"]
                classification = _classify_preflight_value(row[contract.column])
                if classification == "envelope_aes_gcm":
                    classification = _classify_preflight_value(
                        row[contract.column],
                        contract=contract,
                        aad_values=_aad_values_for_row(contract, row),
                    )
                _record_preflight_classification(
                    counts,
                    classification,
                )

        reports.append(
            EncryptedFieldCiphertextReport(
                contract_id=contract.id,
                table=contract.table,
                column=contract.column,
                row_count=counts.row_count,
                scanned_rows=counts.scanned_rows,
                legacy_fernet=counts.legacy_fernet,
                envelope_fernet=counts.envelope_fernet,
                envelope_aes_gcm=counts.envelope_aes_gcm,
                null_empty=counts.null_empty,
                malformed=counts.malformed,
                decrypt_failures=counts.decrypt_failures,
            )
        )

    return reports


def _preflight_blocked_reason_data(
    *,
    capacity_reports: list[EncryptedFieldCapacityReport],
    ciphertext_reports: list[EncryptedFieldCiphertextReport],
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    missing_schema = [
        report.contract_id for report in capacity_reports if report.detail.startswith("missing ")
    ]
    blocked_capacity = [
        report.contract_id
        for report in capacity_reports
        if not report.ready and report.contract_id not in missing_schema
    ]
    malformed_reports = [report.contract_id for report in ciphertext_reports if report.malformed]
    decrypt_failure_reports = [
        report.contract_id for report in ciphertext_reports if not report.decryptable
    ]
    if missing_schema:
        reasons.append({"code": "missing_schema", "contract_ids": missing_schema})
    if blocked_capacity:
        reasons.append({"code": "schema_not_envelope_ready", "contract_ids": blocked_capacity})
    if malformed_reports:
        reasons.append({"code": "malformed_ciphertext", "contract_ids": malformed_reports})
    if decrypt_failure_reports:
        reasons.append({"code": "decryptability_failure", "contract_ids": decrypt_failure_reports})
    return reasons


def _preflight_human_reason_phrases(reasons: list[dict[str, Any]]) -> list[str]:
    phrases = []
    reason_codes = {str(reason["code"]) for reason in reasons}
    if "missing_schema" in reason_codes or "schema_not_envelope_ready" in reason_codes:
        phrases.append("schema is not envelope-ready")
    if "malformed_ciphertext" in reason_codes:
        phrases.append("malformed ciphertext values are present")
    if "decryptability_failure" in reason_codes:
        phrases.append("one or more non-empty values failed decryptability checks")
    return phrases


def _encrypted_field_preflight_report(
    *,
    contracts: tuple[EncryptedFieldContract, ...],
    capacity_reports: list[EncryptedFieldCapacityReport],
    ciphertext_reports: list[EncryptedFieldCiphertextReport],
    alembic_revision: str,
    batch_size: int,
) -> dict[str, Any]:
    capacity_by_contract_id = {report.contract_id: report for report in capacity_reports}
    ciphertext_by_contract_id = {report.contract_id: report for report in ciphertext_reports}
    blocked_reasons = _preflight_blocked_reason_data(
        capacity_reports=capacity_reports,
        ciphertext_reports=ciphertext_reports,
    )
    contract_reports = []
    for contract in contracts:
        capacity = capacity_by_contract_id[contract.id]
        ciphertext_report = ciphertext_by_contract_id.get(contract.id)
        row_counts = {
            "envelope_aes_gcm": 0,
            "envelope_fernet": 0,
            "legacy_fernet": 0,
            "null_empty": 0,
            "scanned": 0,
            "total": 0,
        }
        failures = {"decrypt_failures": 0, "malformed": 0}
        if ciphertext_report is not None:
            row_counts = {
                "envelope_aes_gcm": ciphertext_report.envelope_aes_gcm,
                "envelope_fernet": ciphertext_report.envelope_fernet,
                "legacy_fernet": ciphertext_report.legacy_fernet,
                "null_empty": ciphertext_report.null_empty,
                "scanned": ciphertext_report.scanned_rows,
                "total": ciphertext_report.row_count,
            }
            failures = {
                "decrypt_failures": ciphertext_report.decrypt_failures,
                "malformed": ciphertext_report.malformed,
            }
        contract_ready = (
            capacity.ready and failures["decrypt_failures"] == 0 and failures["malformed"] == 0
        )
        contract_reports.append(
            {
                "capacity": {
                    "detail": capacity.detail,
                    "ready": capacity.ready,
                },
                "column": contract.column,
                "contract_id": contract.id,
                "failures": failures,
                "rows": row_counts,
                "status": "ready" if contract_ready else "blocked",
                "table": contract.table,
            }
        )

    totals = {
        "decrypt_failures": sum(report.decrypt_failures for report in ciphertext_reports),
        "envelope_aes_gcm": sum(report.envelope_aes_gcm for report in ciphertext_reports),
        "envelope_fernet": sum(report.envelope_fernet for report in ciphertext_reports),
        "legacy_fernet": sum(report.legacy_fernet for report in ciphertext_reports),
        "malformed": sum(report.malformed for report in ciphertext_reports),
        "null_empty": sum(report.null_empty for report in ciphertext_reports),
        "rows_scanned": sum(report.scanned_rows for report in ciphertext_reports),
        "rows_total": sum(report.row_count for report in ciphertext_reports),
    }
    return {
        "alembic_revision": alembic_revision,
        "blocked_reasons": blocked_reasons,
        "contract_set": {
            "contract_ids": [contract.id for contract in contracts],
            "version": ENCRYPTED_FIELD_CONTRACT_SET_VERSION,
        },
        "contracts": contract_reports,
        "helper_version": ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
        "report_type": "encrypted-field-preflight",
        "scan": {"batch_size": batch_size},
        "schema_revision": ENCRYPTED_FIELD_PREFLIGHT_SCHEMA_REVISION,
        "status": "blocked" if blocked_reasons else "ready",
        "totals": totals,
    }


def _load_json_artifact(path: Path, artifact_name: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise click.ClickException(f"Cannot read {artifact_name} artifact") from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON in {artifact_name} artifact") from exc
    if not isinstance(data, dict):
        raise click.ClickException(f"Invalid {artifact_name} artifact")
    return data


def _nested_manifest_value(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _require_manifest_value(
    errors: list[str],
    manifest: dict[str, Any],
    path: tuple[str, ...],
    expected: Any,
) -> None:
    value = _nested_manifest_value(manifest, path)
    if value != expected:
        errors.append(f"{'.'.join(path)} must be {expected!r}")


def _require_manifest_string(
    errors: list[str],
    manifest: dict[str, Any],
    path: tuple[str, ...],
) -> None:
    value = _nested_manifest_value(manifest, path)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{'.'.join(path)} must be a non-empty string")


def _release_gate_preflight_errors(preflight_report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_contract_ids = sorted(contract.id for contract in ENCRYPTED_FIELD_CONTRACTS)
    contract_set_value = preflight_report.get("contract_set", {})
    contract_set = contract_set_value if isinstance(contract_set_value, dict) else {}
    contract_ids = contract_set.get("contract_ids")
    totals = preflight_report.get("totals", {})

    if preflight_report.get("report_type") != "encrypted-field-preflight":
        errors.append("preflight artifact report_type must be encrypted-field-preflight")
    if preflight_report.get("status") != "ready":
        errors.append("preflight artifact status must be ready")
    if preflight_report.get("helper_version") != ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION:
        errors.append("preflight artifact helper_version does not match this release")
    if preflight_report.get("schema_revision") != ENCRYPTED_FIELD_PREFLIGHT_SCHEMA_REVISION:
        errors.append("preflight artifact schema_revision does not match this release")
    if contract_set.get("version") != ENCRYPTED_FIELD_CONTRACT_SET_VERSION:
        errors.append("preflight artifact contract_set version does not match this release")
    if (
        not isinstance(contract_ids, list)
        or not all(isinstance(contract_id, str) for contract_id in contract_ids)
        or sorted(contract_ids) != expected_contract_ids
    ):
        errors.append("preflight artifact must cover every encrypted-field contract")
    if not isinstance(totals, dict):
        errors.append("preflight artifact totals must be present")
    else:
        if totals.get("malformed") != 0:
            errors.append("preflight artifact must have zero malformed values")
        if totals.get("decrypt_failures") != 0:
            errors.append("preflight artifact must have zero decrypt failures")
        if totals.get("rows_scanned") != totals.get("rows_total"):
            errors.append("preflight artifact must scan every encrypted-field row")

    contracts = preflight_report.get("contracts", [])
    if not isinstance(contracts, list) or len(contracts) != len(expected_contract_ids):
        errors.append(
            "preflight artifact contract details must cover every encrypted-field contract"
        )
    else:
        blocked_contracts = [
            str(contract.get("contract_id"))
            for contract in contracts
            if not isinstance(contract, dict) or contract.get("status") != "ready"
        ]
        if blocked_contracts:
            errors.append("preflight artifact contains blocked contract results")

    return errors


def _release_gate_manifest_errors(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_true_paths: tuple[tuple[str, ...], ...] = (
        ("release_checks", "migration_tests_passed"),
        ("release_checks", "ciphertext_fit_tests_passed"),
        ("backup_restore_rehearsal", "completed"),
        ("backup_restore_rehearsal", "matching_key_material_verified"),
        ("dry_run", "completed"),
        ("dry_run", "exit_status_zero"),
        ("dry_run", "artifact_archived"),
        ("live_batch_rehearsal", "completed"),
        ("interruption_resume_rehearsal", "completed"),
        ("interruption_resume_rehearsal", "already_migrated_rows_skipped"),
        ("interruption_resume_rehearsal", "remaining_rows_continued"),
        ("rollback_rehearsal", "completed"),
        ("rollback_rehearsal", "old_reader_preserved"),
        ("rollback_rehearsal", "legacy_reads_verified"),
        ("rollback_rehearsal", "target_reads_verified"),
        ("approval", "maintainer_approved"),
        ("zero_downtime", "bounded_batches"),
        ("zero_downtime", "no_full_table_rewrite"),
        ("emergency_rollback", "dual_reader_remains_deployed"),
        ("emergency_rollback", "new_writes_can_revert_to_legacy"),
    )
    expected_false_paths: tuple[tuple[str, ...], ...] = (
        ("zero_downtime", "planned_downtime"),
        ("emergency_rollback", "destructive_down_migration_required"),
    )
    required_string_paths: tuple[tuple[str, ...], ...] = (
        ("preflight_artifact",),
        ("backup_restore_rehearsal", "artifact"),
        ("dry_run", "artifact"),
        ("live_batch_rehearsal", "artifact"),
        ("interruption_resume_rehearsal", "artifact"),
        ("rollback_rehearsal", "artifact"),
        ("approval", "reference"),
        ("approval", "approved_at"),
    )

    _require_manifest_value(
        errors,
        manifest,
        ("report_type",),
        ENCRYPTED_FIELD_PRODUCTION_GATE_MANIFEST_TYPE,
    )
    _require_manifest_value(
        errors,
        manifest,
        ("gate_version",),
        ENCRYPTED_FIELD_PRODUCTION_GATE_MANIFEST_VERSION,
    )
    _require_manifest_value(
        errors,
        manifest,
        ("target_format",),
        ENCRYPTED_FIELD_MIGRATION_TARGET_FORMAT.value,
    )
    _require_manifest_value(
        errors,
        manifest,
        ("helper_version",),
        ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
    )
    _require_manifest_value(
        errors,
        manifest,
        ("contract_set_version",),
        ENCRYPTED_FIELD_CONTRACT_SET_VERSION,
    )
    for path in expected_true_paths:
        _require_manifest_value(errors, manifest, path, True)
    for path in expected_false_paths:
        _require_manifest_value(errors, manifest, path, False)
    for path in required_string_paths:
        _require_manifest_string(errors, manifest, path)

    approved_by = _nested_manifest_value(manifest, ("approval", "approved_by"))
    if (
        not isinstance(approved_by, list)
        or not approved_by
        or not all(isinstance(name, str) and name.strip() for name in approved_by)
    ):
        errors.append("approval.approved_by must list at least one maintainer")

    return errors


def register_encrypted_field_commands(app: Flask) -> None:
    encrypted_field_cli = AppGroup(
        "encrypted-field",
        help="Encrypted-field migration and rollout commands",
    )

    @encrypted_field_cli.command("preflight")
    @click.option(
        "--output",
        "output_format",
        type=click.Choice(("human", "json")),
        default="human",
        show_default=True,
        help="Output format.",
    )
    @click.option(
        "--contract",
        "contract_ids",
        multiple=True,
        help="Limit the run to one encrypted-field contract ID. May be repeated.",
    )
    @click.option(
        "--batch-size",
        type=click.IntRange(min=1),
        default=1000,
        show_default=True,
        help="Maximum rows to fetch per scan query.",
    )
    def preflight(output_format: str, contract_ids: tuple[str, ...], batch_size: int) -> None:
        """Report encrypted-field envelope rollout readiness without mutating data."""
        contracts = _selected_contracts(contract_ids)
        capacity_reports = _encrypted_field_column_capacity_reports(contracts)
        ciphertext_reports = _classify_encrypted_field_values(
            contracts=contracts,
            batch_size=batch_size,
        )
        alembic_revision = _current_alembic_revision()
        preflight_report = _encrypted_field_preflight_report(
            contracts=contracts,
            capacity_reports=capacity_reports,
            ciphertext_reports=ciphertext_reports,
            alembic_revision=alembic_revision,
            batch_size=batch_size,
        )
        blocked_reasons = preflight_report["blocked_reasons"]

        if output_format == "json":
            click.echo(json.dumps(preflight_report, indent=2, sort_keys=True))
            if blocked_reasons:
                raise click.exceptions.Exit(1)
            return

        click.echo(f"Current Alembic revision: {alembic_revision}")
        click.echo(f"Scan batch size: {batch_size}")
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
                f"envelope AES-GCM: {ciphertext_report.envelope_aes_gcm}; "
                f"null/empty: {ciphertext_report.null_empty}; "
                f"malformed: {ciphertext_report.malformed}; "
                f"decrypt failures: {ciphertext_report.decrypt_failures}; "
                f"decryptable: {'yes' if ciphertext_report.decryptable else 'no'}"
            )

        if blocked_reasons:
            reasons = _preflight_human_reason_phrases(blocked_reasons)
            raise click.ClickException(
                "Encrypted-field preflight readiness: blocked (" + "; ".join(reasons) + ")"
            )

        click.echo("Encrypted-field preflight readiness: ready")

    @encrypted_field_cli.command("release-gate")
    @click.option(
        "--preflight-artifact",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="Redacted JSON artifact produced by encrypted-field preflight --output json.",
    )
    @click.option(
        "--evidence-manifest",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="Redacted production release-gate evidence manifest.",
    )
    def release_gate(preflight_artifact: Path, evidence_manifest: Path) -> None:
        """Validate production envelope-write evidence before configuration changes."""
        preflight_report = _load_json_artifact(preflight_artifact, "preflight")
        manifest = _load_json_artifact(evidence_manifest, "release-gate manifest")
        errors = _release_gate_preflight_errors(preflight_report)
        errors.extend(_release_gate_manifest_errors(manifest))
        if errors:
            raise click.ClickException(
                "Encrypted-field production release gate: blocked (" + "; ".join(errors) + ")"
            )

        click.echo("Encrypted-field production release gate: ready")
        click.echo(f"Target format: {ENCRYPTED_FIELD_MIGRATION_TARGET_FORMAT.value}")
        click.echo(f"Preflight artifact: {preflight_artifact}")
        click.echo(f"Evidence manifest: {evidence_manifest}")
        click.echo("Downtime plan: zero planned downtime with bounded batches")
        click.echo(
            "Rollback safety: dual reader remains deployed; "
            "new writes can revert to legacy-fernet"
        )

    @encrypted_field_cli.command("migrate")
    @click.option(
        "--dry-run",
        "mode",
        flag_value="dry-run",
        default="dry-run",
        help="Verify and report encrypted-field rewrites without writing.",
    )
    @click.option(
        "--live",
        "mode",
        flag_value="live",
        help="Rewrite verified encrypted-field rows and commit the bounded batch.",
    )
    @click.option(
        "--batch-size",
        type=click.IntRange(min=1),
        default=100,
        show_default=True,
        help="Maximum rows to examine in this run.",
    )
    @click.option(
        "--contract",
        "contract_ids",
        multiple=True,
        help="Limit the run to one encrypted-field contract ID. May be repeated.",
    )
    @click.option(
        "--resume-token",
        help="Resume from a prior run's next resume token.",
    )
    @click.option(
        "--full-scan",
        is_flag=True,
        help="Ignore the resume token position and scan selected contracts from the start.",
    )
    @click.option(
        "--target-format",
        default=ENCRYPTED_FIELD_MIGRATION_TARGET_FORMAT.value,
        show_default=True,
        help="Target encrypted-field write format.",
    )
    def migrate(  # noqa: PLR0913
        mode: str,
        batch_size: int,
        contract_ids: tuple[str, ...],
        resume_token: str | None,
        full_scan: bool,
        target_format: str,
    ) -> None:
        """Dry-run or live migrate encrypted fields to the envelope target format."""
        try:
            parsed_target_format = EncryptedFieldWriteFormat.parse(target_format)
        except ConfigParseError as exc:
            raise click.ClickException(str(exc)) from exc
        if parsed_target_format != ENCRYPTED_FIELD_MIGRATION_TARGET_FORMAT:
            raise click.ClickException(
                "Encrypted-field migration only supports target format "
                f"{ENCRYPTED_FIELD_MIGRATION_TARGET_FORMAT.value}"
            )

        contracts = _selected_contracts(contract_ids)
        selected_contract_ids = tuple(contract.id for contract in contracts)
        resume_state = None
        if resume_token:
            resume_state = _parse_resume_state(
                resume_token,
                batch_size=batch_size,
                contract_ids=selected_contract_ids,
                target_format=parsed_target_format,
            )

        started = time.monotonic()
        try:
            reports, next_resume_state = _run_encrypted_field_migration_batch(
                contracts=contracts,
                dry_run=mode == "dry-run",
                batch_size=batch_size,
                resume_state=resume_state,
                full_scan=full_scan,
                target_format=parsed_target_format,
            )
        except EncryptedFieldMigrationError as exc:
            db.session.rollback()
            raise click.ClickException(
                "Encrypted-field migration failed: " + exc.failure.safe_message()
            ) from exc

        _print_migration_reports(
            reports=reports,
            dry_run=mode == "dry-run",
            batch_size=batch_size,
            target_format=parsed_target_format,
            next_resume_state=next_resume_state,
            elapsed_seconds=time.monotonic() - started,
        )

    app.cli.add_command(encrypted_field_cli)
