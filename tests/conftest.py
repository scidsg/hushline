import os
from typing import Generator

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline import create_app, db

# TODO once we refactor `fernet` to not be global, move this into the `config` fixture.
# this needs to be imported before importing `hushline`
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()


@pytest.fixture()
def _config(mocker: MockFixture) -> None:
    mocker.patch.dict(os.environ, {})


@pytest.fixture()
def app(_config: None) -> Generator[Flask, None, None]:
    os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    os.environ["SQLALCHEMY_TRACK_MODIFICATIONS"] = "False"
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    os.environ["IS_PERSONAL_SERVER"] = "True"

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost:8080"
    app.config["PREFERRED_URL_SCHEME"] = "http"

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture()
def client(app: Flask) -> Generator[FlaskClient, None, None]:
    with app.test_client() as client:
        yield client
