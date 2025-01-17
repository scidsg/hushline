from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def load_data(self) -> None:
        pass

    def check_upgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM field_definitions")) == 0
        assert db.session.scalar(text("SELECT count(*) FROM field_values")) == 0


class DowngradeTester:
    """Nothing to do. It's just table drops."""

    def load_data(self) -> None:
        pass

    def check_downgrade(self) -> None:
        pass
