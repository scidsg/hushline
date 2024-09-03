import os
from typing import Generator

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline import create_app, db
from hushline.model import Tier

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

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost:8080"
    app.config["PREFERRED_URL_SCHEME"] = "http"

    with app.app_context():
        db.create_all()

        # Create the default tiers
        # (this happens in the migrations, but migrations don't run in the tests)
        db.session.add(Tier(name="Free", monthly_amount=0))
        db.session.add(Tier(name="Business", monthly_amount=2000))
        db.session.commit()

        yield app
        db.drop_all()


@pytest.fixture()
def client(app: Flask) -> Generator[FlaskClient, None, None]:
    with app.test_client() as client:
        yield client
