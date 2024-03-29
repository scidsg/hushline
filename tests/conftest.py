import os
from typing import Generator

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from pytest_mock import MockFixture

# TODO once we refactor `fernet` to not be global, move this into the `config` fixture.
# this needs to be imported before importing `hushline`
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from hushline import create_app  # noqa: E402


@pytest.fixture(scope="function")
def config(mocker: MockFixture) -> None:
    mocker.patch.dict(os.environ, {})


@pytest.fixture(scope="function")
def app(config: None) -> Generator[Flask, None, None]:
    app_ = create_app()
    app_.config["SERVER_NAME"] = "localhost:5000"
    app_.config["PREFERRED_URL_SCHEME"] = "http"
    with app_.app_context():
        yield app_
