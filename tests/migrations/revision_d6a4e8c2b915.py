"""Paid-invoice migration preserves the account-independent annual obligation."""

from sqlalchemy import text

from hushline.db import db
from tests.migrations.revision_8c6f1e2a9b04 import ORDER_ID, _order, _user


class UpgradeTester:
    def load_data(self) -> None:
        _user()
        _order()

    def check_upgrade(self) -> None:
        db.session.execute(
            text("UPDATE single_tenant_orders SET stripe_invoice_id='in_migration' WHERE id=:id"),
            {"id": ORDER_ID},
        )
        db.session.commit()
        assert (
            db.session.scalar(
                text("SELECT stripe_invoice_id FROM single_tenant_orders WHERE id=:id"),
                {"id": ORDER_ID},
            )
            == "in_migration"
        )
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
        assert (
            db.session.scalar(
                text("SELECT paid FROM single_tenant_orders WHERE id=:id"), {"id": ORDER_ID}
            )
            is True
        )
        assert (
            db.session.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name='single_tenant_orders' "
                    "AND column_name='stripe_invoice_id'"
                )
            )
            == 0
        )
