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
from flask import Flask

from hushline.db import db, migrate

REVISIONS_ROOT = Path(__file__).parent.parent / "migrations"
assert REVISIONS_ROOT.exists()
assert REVISIONS_ROOT.is_dir()


FIRST_TESTABLE_REVISION = "46aedec8fd9b"
SKIPPABLE_REVISIONS = [
    "5ffe5a5c8e9a",  # only renames indices and tables, no data changed
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


@pytest.mark.parametrize("revision", TESTABLE_REVISIONS)
def test_downgrade_with_data(revision: str, app: Flask) -> None:
    cfg = typing.cast(alembic.config.Config, migrate.get_config())
    command.upgrade(cfg, revision)

    mod = __import__(f"tests.migrations.revision_{revision}", fromlist=["DowngradeTester"])
    downgrade_tester = mod.DowngradeTester()

    downgrade_tester.load_data()
    db.session.close()

    command.downgrade(cfg, "-1")
    downgrade_tester.check_downgrade()