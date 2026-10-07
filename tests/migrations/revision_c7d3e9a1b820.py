"""Replay-protection migration leaves billing obligations intact."""

from sqlalchemy import text

from hushline.db import db
from tests.migrations.revision_8c6f1e2a9b04 import ORDER_ID, _order, _user


class UpgradeTester:
    def load_data(self) -> None:
        _user()
        _order()

    def check_upgrade(self) -> None:
        db.session.execute(
            text("INSERT INTO single_tenant_nonces (nonce, seen) VALUES (:nonce, 1791280800)"),
            {"nonce": "a" * 32},
        )
        db.session.commit()
        assert db.session.scalar(text("SELECT count(*) FROM single_tenant_nonces")) == 1
        assert (
            db.session.scalar(
                text("SELECT paid FROM single_tenant_orders WHERE id=:id"), {"id": ORDER_ID}
            )
            is True
        )


class DowngradeTester:
    def load_data(self) -> None:
        _user()
        _order()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT to_regclass('single_tenant_nonces')")) is None
        assert (
            db.session.scalar(
                text("SELECT paid FROM single_tenant_orders WHERE id=:id"), {"id": ORDER_ID}
            )
            is True
        )
