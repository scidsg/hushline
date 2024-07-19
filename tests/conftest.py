import os
import secrets
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline import create_app, db
from hushline.crypto.secrets_manager import SecretsManager

TEST_ADMIN_SECRET: bytearray = bytearray(secrets.token_bytes(32))
vault = SecretsManager(TEST_ADMIN_SECRET.copy())


@pytest.fixture()
def _config(mocker: MockFixture) -> None:
    mocker.patch.dict(os.environ, {})


@pytest.fixture(params=["environment", "interactive"])
def app(
    _config: None, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Generator[Flask, None, None]:
    os.environ["ADMIN_INPUT_SOURCE"] = request.param
    os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    os.environ["SQLALCHEMY_TRACK_MODIFICATIONS"] = "False"
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"

    def mock_getpass(prompt: str) -> str:
        return TEST_ADMIN_SECRET.hex()

    monkeypatch.setattr("getpass.getpass", mock_getpass)
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


@pytest.fixture(scope="session")
def session_monkeypatch(
    request: pytest.FixtureRequest,
) -> Generator[pytest.MonkeyPatch, None, None]:
    monkeypatch = pytest.MonkeyPatch()

    yield monkeypatch

    monkeypatch.undo


@pytest.fixture(params=["environment", "interactive"], scope="session")
def static_app(
    session_monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Generator[Flask, None, None]:
    """A faster app fixture. Should only be used in tests which *do not* leave
    the environment or app state mutated from its initial state.
    """
    os.environ["ADMIN_INPUT_SOURCE"] = request.param
    os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    os.environ["SQLALCHEMY_TRACK_MODIFICATIONS"] = "False"
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"

    def mock_getpass(prompt: str) -> str:
        return TEST_ADMIN_SECRET.hex()

    session_monkeypatch.setattr("getpass.getpass", mock_getpass)
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost:8080"
    app.config["PREFERRED_URL_SCHEME"] = "http"

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope="session")
def static_client(static_app: Flask) -> Generator[FlaskClient, None, None]:
    with static_app.test_client() as client:
        yield client
