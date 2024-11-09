import json

from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def __init__(self) -> None:
        self.name = "wat"
        self.color = "#acab00"

    def load_data(self) -> None:
        db.session.execute(text("truncate host_organization"))

        db.session.execute(
            text(
                """
            INSERT INTO host_organization (id, brand_app_name, brand_primary_hex_color)
            VALUES (1, :name, :color)
            """
            ),
            dict(color=self.color, name=self.name),
        )

        db.session.commit()

    def check_upgrade(self) -> None:
        rows = db.session.execute(db.text("SELECT * FROM organization_settings"))
        settings = {x[0]: x[1] for x in rows}
        assert settings["brand_name"] == self.name
        assert settings["brand_primary_color"] == self.color


class DowngradeTester:
    def __init__(self) -> None:
        self.name = "wat"
        self.color = "#acab00"

    def load_data(self) -> None:
        db.session.execute(text("truncate organization_settings"))

        db.session.execute(
            text(
                """
            INSERT INTO organization_settings (key, value)
            VALUES ('brand_name', :name), ('brand_primary_color', :color)
            """
            ),
            dict(color=json.dumps(self.color), name=json.dumps(self.name)),
        )

        db.session.commit()

    def check_downgrade(self) -> None:
        rows = list(
            db.session.execute(
                db.text(
                    """
            SELECT id, brand_app_name, brand_primary_hex_color
            FROM host_organization
            """
                )
            )
        )
        assert len(rows) == 1
        assert rows[0][0] == 1
        assert rows[0][1] == self.name
        assert rows[0][2] == self.color
