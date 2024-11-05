import os
from typing import Callable

import pytest
from flask import Flask, url_for
from pytest_mock import MockFixture


@pytest.fixture()
def env_var_modifier() -> Callable[[MockFixture], None]:
    def modifier(mocker: MockFixture) -> None:
        mocker.patch.dict(os.environ, {"ONION_HOSTNAME": "example.onion"})

    return modifier


def test_info_available(app: Flask) -> None:
    with app.test_client() as client:
        response = client.get(url_for("server_info"))
        assert response.status_code == 200
        assert "Hush Line Server Info" in response.get_data(as_text=True)
        assert "example.onion" in response.get_data(as_text=True)
