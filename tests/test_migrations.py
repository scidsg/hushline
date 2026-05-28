"""
This module dynamically generates test cases from the revisions directory.
To create new test modules, look at the "revision_tests" directory for examples.
"""

import typing
from pathlib import Path
from typing import Sequence

import alembic.config
import pytest
from alembic import command
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import text

from hushline import crypto
from hushline.config import ENCRYPTED_FIELD_WRITE_FORMAT, EncryptedFieldWriteFormat
from hushline.db import db, migrate
from tests.migrations.revision_b2039e7c0a1d import (
    ENCRYPTED_COLUMNS,
    LEGACY_FERNET_KEY,
)

REVISIONS_ROOT = Path(__file__).parent.parent / "migrations"
assert REVISIONS_ROOT.exists()
assert REVISIONS_ROOT.is_dir()


FIRST_TESTABLE_REVISION = "46aedec8fd9b"
SKIPPABLE_REVISIONS = [
    "5ffe5a5c8e9a",  # only renames indices and tables, no data changed
    "06b343c38386",  # only renames indices and tables, no data changed
    "6071f1eea074",  # simple add/drop on columns, no data migrated
    "f32aa741ddc4",  # simple add/drop on columns, no data migrated
    "7b9c2d1e4f60",  # simple add/drop on columns, no data migrated
    "a4c8f2d9e713",  # simple table create/drop, no data migrated
]
DISALLOWED_DOWNGRADES = [
    "4a53667aff6e",  # downgrading is disabled to prevent accidental data loss
]


def list_revisions() -> Sequence[str]:
    script_dir = ScriptDirectory(str(REVISIONS_ROOT))
    revisions = list(script_dir.walk_revisions())
    revisions.reverse()
    return [x.module.revision for x in revisions]


def list_testable_revisions() -> Sequence[str]:
    idx = ALL_REVISIONS.index(FIRST_TESTABLE_REVISION)
    assert idx >= 0
    return [rev for rev in ALL_REVISIONS[idx:] if rev not in SKIPPABLE_REVISIONS]


ALL_REVISIONS: Sequence[str] = list_revisions()
TESTABLE_REVISIONS: Sequence[str] = list_testable_revisions()


def test_linear_revision_history(app: Flask) -> None:
    script_dir = ScriptDirectory.from_config(
        typing.cast(alembic.config.Config, migrate.get_config())
    )

    bases = script_dir.get_bases()
    assert len(bases) == 1, f"Multiple bases found: {bases}"
    assert bases[0] == ALL_REVISIONS[0]

    heads = script_dir.get_heads()
    assert len(heads) == 1, f"Multiple heads found: {heads}"
    assert heads[0] == ALL_REVISIONS[-1]


@pytest.mark.parametrize("revision", TESTABLE_REVISIONS)
def test_upgrade_with_data(revision: str, app: Flask) -> None:
    previous_revision = ALL_REVISIONS[ALL_REVISIONS.index(revision) - 2]
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, previous_revision)

    mod = __import__(f"tests.migrations.revision_{revision}", fromlist=["UpgradeTester"])
    upgrade_tester = mod.UpgradeTester()

    upgrade_tester.load_data()
    db.session.close()

    command.upgrade(cfg, revision)
    upgrade_tester.check_upgrade()

    # absurd but somehow we need to check this
    assert db.session.scalar(text("SELECT version_num FROM alembic_version")) == revision


@pytest.mark.parametrize("revision", TESTABLE_REVISIONS)
def test_downgrade_with_data(revision: str, app: Flask) -> None:
    if revision in DISALLOWED_DOWNGRADES:
        pytest.xfail("Downgrade is disallowed for this revision")

    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, revision)

    mod = __import__(f"tests.migrations.revision_{revision}", fromlist=["DowngradeTester"])
    downgrade_tester = mod.DowngradeTester()

    downgrade_tester.load_data()
    db.session.close()

    command.downgrade(cfg, "-1")
    downgrade_tester.check_downgrade()

    # absurd but somehow we need to check this
    assert (
        db.session.scalar(text("SELECT version_num FROM alembic_version"))
        == ALL_REVISIONS[ALL_REVISIONS.index(revision) - 1]
    )


@pytest.mark.parametrize("revision", TESTABLE_REVISIONS)
def test_double_upgrade(revision: str, app: Flask) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, revision)
    command.upgrade(cfg, revision)


@pytest.mark.parametrize(
    ("table_name", "column_name"),
    crypto.ENCRYPTED_FIELD_ENVELOPE_READY_COLUMNS,
)
def test_encrypted_column_downgrade_refuses_oversized_ciphertext(
    table_name: str,
    column_name: str,
    app: Flask,
) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, "b2039e7c0a1d")

    mod = __import__(
        "tests.migrations.revision_b2039e7c0a1d",
        fromlist=["DowngradeGuardTester"],
    )
    downgrade_guard_tester = mod.DowngradeGuardTester(table_name, column_name)
    downgrade_guard_tester.load_data()
    db.session.close()

    expected_column = rf"{table_name}\.{column_name}"
    with pytest.raises(RuntimeError, match=expected_column + r".*exceed 255 characters"):
        command.downgrade(cfg, "-1")

    db.session.rollback()
    downgrade_guard_tester.check_value_preserved()


def test_envelope_schema_readiness_columns_match_widening_migration() -> None:
    mod = __import__(
        "migrations.versions.b2039e7c0a1d_widen_encrypted_columns_for_envelopes",
        fromlist=["ENCRYPTED_SHORT_STRING_COLUMNS"],
    )

    assert ENCRYPTED_COLUMNS == mod.ENCRYPTED_SHORT_STRING_COLUMNS
    assert crypto.ENCRYPTED_FIELD_ENVELOPE_READY_COLUMNS == mod.ENCRYPTED_SHORT_STRING_COLUMNS


def test_encrypted_field_preflight_tracks_widening_migration_readiness(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, "a4c8f2d9e713")
    monkeypatch.setenv("ENCRYPTION_KEY", LEGACY_FERNET_KEY)
    runner = app.test_cli_runner()

    pre_migration_result = runner.invoke(args=["encrypted-field", "preflight"])

    assert pre_migration_result.exit_code == 1
    assert "Current Alembic revision: a4c8f2d9e713" in pre_migration_result.output
    for table_name, column_name in crypto.ENCRYPTED_FIELD_ENVELOPE_READY_COLUMNS:
        assert f"({table_name}.{column_name}): blocked (length 255)" in (
            pre_migration_result.output
        )
    assert "Encrypted-field preflight readiness: blocked" in pre_migration_result.output
    assert "schema is not envelope-ready" in pre_migration_result.output

    db.session.close()
    command.upgrade(cfg, "b2039e7c0a1d")

    post_migration_result = runner.invoke(args=["encrypted-field", "preflight"])

    assert post_migration_result.exit_code == 0
    assert "Current Alembic revision: b2039e7c0a1d" in post_migration_result.output
    for table_name, column_name in crypto.ENCRYPTED_FIELD_ENVELOPE_READY_COLUMNS:
        assert f"({table_name}.{column_name}): ready (unbounded)" in (post_migration_result.output)
    assert "Encrypted-field preflight readiness: ready" in post_migration_result.output


def test_legacy_encrypted_field_writes_do_not_require_envelope_schema(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, "a4c8f2d9e713")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET

    encrypted = crypto.encrypt_field("secret")

    assert encrypted is not None
    assert not encrypted.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(encrypted) == "secret"


def test_envelope_encrypted_field_writes_reject_pre_migration_schema(app: Flask) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, "a4c8f2d9e713")
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET

    with pytest.raises(crypto.EncryptedFieldSchemaNotReadyError) as excinfo:
        crypto.encrypt_field("secret")

    message = str(excinfo.value)
    assert "Run migration b2039e7c0a1d" in message
    for table_name, column_name in crypto.ENCRYPTED_FIELD_ENVELOPE_READY_COLUMNS:
        assert f"{table_name}.{column_name}" in message


def test_envelope_encrypted_field_writes_accept_widened_schema(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, "b2039e7c0a1d")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET

    encrypted = crypto.encrypt_field("secret")

    assert encrypted is not None
    assert encrypted.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(encrypted) == "secret"


def test_downgrade_preserves_mixed_ciphertexts_readable_by_dual_reader(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, "b2039e7c0a1d")
    monkeypatch.setenv("ENCRYPTION_KEY", LEGACY_FERNET_KEY)
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET

    mod = __import__(
        "tests.migrations.revision_b2039e7c0a1d",
        fromlist=["RollbackReadabilityTester"],
    )
    rollback_tester = mod.RollbackReadabilityTester()
    rollback_tester.load_data()
    db.session.close()

    command.downgrade(cfg, "-1")
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET

    for encrypted_value in rollback_tester.encrypted_values():
        decrypted_value = crypto.decrypt_field(encrypted_value)
        assert decrypted_value is not None
        assert decrypted_value.startswith(("legacy", "recipient", "safe", "smtp.legacy"))

    post_rollback_ciphertext = crypto.encrypt_field("post-rollback secret")
    assert post_rollback_ciphertext is not None
    assert not post_rollback_ciphertext.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(post_rollback_ciphertext) == "post-rollback secret"
