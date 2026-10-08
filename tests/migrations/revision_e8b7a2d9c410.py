"""Launch migration preserves existing paid orders and durable destruction intent."""

from sqlalchemy import text

from hushline.db import db
from tests.migrations.revision_8c6f1e2a9b04 import ORDER_ID, _order, _user


class UpgradeTester:
    def load_data(self) -> None:
        _user()
        _order()

    def check_upgrade(self) -> None:
        row = db.session.execute(
            text(
                "SELECT paid, stripe_free_coupon_id, destroy_requested_at, destruction_pending "
                "FROM single_tenant_orders WHERE id=:id"
            ),
            {"id": ORDER_ID},
        ).one()
        assert tuple(row) == (True, None, None, False)
        db.session.execute(
            text(
                "UPDATE single_tenant_orders SET stripe_free_coupon_id='gift_migration', "
                "destroy_requested_at='2026-10-07T00:00:00+00:00', "
                "destruction_pending=true WHERE id=:id"
            ),
            {"id": ORDER_ID},
        )
        db.session.commit()
        assert (
            db.session.scalar(
                text("SELECT destruction_pending FROM single_tenant_orders WHERE id=:id"),
                {"id": ORDER_ID},
            )
            is True
        )


class DowngradeTester:
    def load_data(self) -> None:
        _user()
        _order()
        db.session.execute(
            text(
                "UPDATE single_tenant_orders SET stripe_free_coupon_id='gift_migration', "
                "destroy_requested_at='2026-10-07T00:00:00+00:00', "
                "destruction_pending=true WHERE id=:id"
            ),
            {"id": ORDER_ID},
        )
        db.session.commit()

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
                    "AND column_name IN ('stripe_free_coupon_id', 'destroy_requested_at', "
                    "'destruction_pending')"
                )
            )
            == 0
        )
