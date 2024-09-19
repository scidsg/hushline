#!/usr/bin/env python
from hushline import create_app
from hushline.db import db
from hushline.model import Tier


def main() -> None:
    with create_app().app_context():
        db.create_all()

        # Add tiers
        tiers = [
            Tier(name="Free", monthly_amount=0),
            Tier(name="Business", monthly_amount=2000),
        ]
        db.session.bulk_save_objects(tiers)
        db.session.commit()


if __name__ == "__main__":
    main()
