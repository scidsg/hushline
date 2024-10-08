import os
from typing import Callable

import pytest
from flask import Flask, url_for
from pytest_mock import MockFixture


@pytest.fixture()
def env_var_modifier(mocker: MockFixture) -> Callable[[MockFixture], None]:
    def modifier(mocker: MockFixture) -> None:
        mocker.patch.dict(os.environ, {"ONION_HOSTNAME": "example.onion"})

    return modifier


def test_info_available_on_personal_server(app: Flask) -> None:
    app.config["IS_PERSONAL_SERVER"] = True

    with app.test_client() as client:
        response = client.get(url_for("personal_server_info"))
        assert response.status_code == 200
        assert "Hush Line Personal Server" in response.get_data(as_text=True)
        assert "example.onion" in response.get_data(as_text=True)


def test_info_not_available_by_default(app: Flask) -> None:
    app.config["IS_PERSONAL_SERVER"] = False

    with app.test_client() as client:
        response = client.get(url_for("personal_server_info"))
        assert response.status_code == 404
