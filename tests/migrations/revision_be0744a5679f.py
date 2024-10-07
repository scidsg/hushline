from typing import Any, Dict

from hushline.db import db

from ..helpers import (  # type: ignore[misc]
    format_param_dict,
    random_bool,
)


class UpgradeTester:
    def __init__(self) -> None:
        self.old_users_count = 10

    def load_data(self) -> None:
        for user_idx in range(self.old_users_count):
            db.session.execute(
                db.text(
                    """
        INSERT INTO users (password_hash, is_admin)
        VALUES ('$scrypt$', :is_admin)
        """
                ),
                dict(is_admin=random_bool()),
            )

        db.session.commit()

    def check_upgrade(self) -> None:
        new_user_count = db.session.execute(db.text("SELECT count(*) FROM users")).scalar()
        # just make sure nothing weird happened where users got dropped
        assert new_user_count == self.old_users_count


class DowngradeTester:
    def __init__(self) -> None:
        self.new_user_count = 10

    def load_data(self) -> None:
        for i in range(1, self.new_user_count + 1):
            params: Dict[str, Any] = {
                "id": i,
                "name": f"tier_{i}",
                "monthly_amount": i * 100,
                "stripe_product_id": f"prod_{i}",
                "stripe_price_id": f"price_{i}",
            }

            columns, param_args = format_param_dict(params)
            db.session.execute(
                db.text(f"INSERT INTO tiers ({columns}) VALUES ({param_args})"), params
            )

            params = {
                "id": i,
                "is_admin": False,
                "password_hash": "$scrypt$",
                "tier_id": i,
                "stripe_customer_id": f"cust_{i}",
                "stripe_subscription_id": f"sub_{i}",
                "stripe_subscription_cancel_at_period_end": False,
            }

            columns, param_args = format_param_dict(params)
            db.session.execute(
                db.text(f"INSERT INTO users ({columns}) VALUES ({param_args})"),
                params,
            )

        db.session.commit()

    def check_downgrade(self) -> None:
        old_user_count = db.session.execute(db.text("SELECT count(*) FROM users")).scalar()
        # just make sure nothing weird happened where users got dropped
        assert old_user_count == self.new_user_count
