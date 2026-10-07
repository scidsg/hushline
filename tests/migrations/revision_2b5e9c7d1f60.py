"""Independent billing identifiers remain unique and survive portal deletion."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db
from tests.migrations.revision_8c6f1e2a9b04 import ORDER_ID, USER_ID, _order, _user


class UpgradeTester:
    def load_data(self) -> None:
        _user()

    def check_upgrade(self) -> None:
        _order()
        db.session.execute(
            text(
                "UPDATE single_tenant_orders SET billing_receipt=:receipt, "
                "stripe_session_id='cs_owned', stripe_subscription_id='sub_owned', "
                "period_start='2026-10-06T00:00:00+00:00', "
                "period_end='2027-10-06T00:00:00+00:00' WHERE id=:id"
            ),
            {"receipt": "e" * 32, "id": ORDER_ID},
        )
        db.session.commit()
        assert (
            db.session.scalar(
                text("SELECT billing_sync_pending FROM single_tenant_orders WHERE id=:id"),
                {"id": ORDER_ID},
            )
            is False
        )
        try:
            db.session.execute(
                text(
                    "INSERT INTO single_tenant_orders "
                    "(id, owner_ref, stage, service_state, domain, paid, cancelled, "
                    "cancellation_pending, billing_receipt) "
                    "VALUES (:id, :owner, 'ready', 'active', '', true, false, false, :receipt)"
                ),
                {"id": "f" * 32, "owner": "f" * 64, "receipt": "e" * 32},
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("Billing receipts must never be shared by orders")
        db.session.execute(text("DELETE FROM users WHERE id=:id"), {"id": USER_ID})
        db.session.commit()
        row = db.session.execute(
            text(
                "SELECT user_id, billing_receipt, stripe_subscription_id, period_end "
                "FROM single_tenant_orders WHERE id=:id"
            ),
            {"id": ORDER_ID},
        ).one()
        assert tuple(row) == (None, "e" * 32, "sub_owned", "2027-10-06T00:00:00+00:00")


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
                    "WHERE table_name='single_tenant_orders' AND column_name='billing_receipt'"
                )
            )
            == 0
        )
