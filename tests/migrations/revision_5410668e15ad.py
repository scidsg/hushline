from hushline.db import db


class UpgradeTester:
    def load_data(self) -> None:
        pass  # migration loads data itself

    def check_upgrade(self) -> None:
        rows = list(db.session.execute(db.text("SELECT * FROM host_organization")))
        assert len(rows) == 1

        row = rows[0]._asdict()
        assert row["id"] == 1


class DowngradeTester:
    """Nothing to do. It's just a table drop."""

    def load_data(self) -> None:
        pass

    def check_downgrade(self) -> None:
        pass
