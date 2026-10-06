"""Single Tenant ownership survives portal deletion; migration is additive."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db

USER_ID = 2419002
ORDER_ID = "a" * 32


def _user() -> None:
    db.session.execute(
        text(
            "INSERT INTO users (id, is_admin, is_suspended, password_hash, session_id) "
            "VALUES (:id, false, false, '$scrypt$', 'migration-single-tenant')"
        ),
        {"id": USER_ID},
    )
    db.session.commit()


def _order() -> None:
    db.session.execute(
        text(
            "INSERT INTO single_tenant_orders "
            "(id, user_id, owner_ref, stage, service_state, domain, paid, cancelled, "
            "cancellation_pending) VALUES (:id, :user_id, :owner, 'ready', 'active', "
            "'fixture.invalid', true, true, true)"
        ),
        {"id": ORDER_ID, "user_id": USER_ID, "owner": "b" * 64},
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _user()

    def check_upgrade(self) -> None:
        _order()
        try:
            db.session.execute(
                text(
                    "INSERT INTO single_tenant_orders "
                    "SELECT :new_id, user_id, :new_owner, license_limit, stage, service_state, "
                    "domain, paid, cancelled, cancellation_pending, period_end "
                    "FROM single_tenant_orders WHERE id = :id"
                ),
                {"new_id": "c" * 32, "new_owner": "d" * 64, "id": ORDER_ID},
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("One account cannot adopt a second order")
        db.session.execute(text("DELETE FROM users WHERE id = :id"), {"id": USER_ID})
        db.session.commit()
        row = db.session.execute(
            text(
                "SELECT user_id, owner_ref, paid, cancelled, cancellation_pending "
                "FROM single_tenant_orders WHERE id = :id"
            ),
            {"id": ORDER_ID},
        ).one()
        assert tuple(row) == (None, "b" * 64, True, True, True)


class DowngradeTester:
    def load_data(self) -> None:
        _user()
        _order()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT to_regclass('public.single_tenant_orders')")) is None
        assert (
            db.session.scalar(text("SELECT count(*) FROM users WHERE id = :id"), {"id": USER_ID})
            == 1
        )
