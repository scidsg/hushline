import os
import random
import string
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator
from uuid import uuid4

import flask_migrate
import pytest
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from hushline import create_app
from hushline.crypto import _SCRYPT_PARAMS
from hushline.db import db
from hushline.model import Message, Tier, User, Username

if TYPE_CHECKING:
    from _pytest.config.argparsing import Parser
else:
    Parser = Any


CONN_FMT_STR = "postgresql+psycopg://hushline:hushline@postgres:5432/{database}"
TEMPLATE_DB_NAME = "app_db_template"


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--alembic",
        action="store_true",
        help="Use alembic migrations for DB initialization",
    )


def random_name(size: int) -> str:
    return "".join([random.choice(string.ascii_lowercase) for _ in range(size)])  # noqa: S311


@contextmanager
def temp_session(conn_str: str) -> Generator[Session, None, None]:
    engine = create_engine(conn_str)
    engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    session = sessionmaker(bind=engine)()

    yield session

    # aggressively terminate all connections
    session.close()
    session.connection().connection.invalidate()
    engine.dispose()


@pytest.fixture(scope="session")
def _db_template(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """A template database that all other databases are created from.
    Effectively allows caching of `db.create_all()`"""

    conn_str = CONN_FMT_STR.format(database="hushline")

    counter = 5
    while True:
        try:
            with temp_session(conn_str) as session:
                session.execute(text(f"CREATE DATABASE {TEMPLATE_DB_NAME} WITH TEMPLATE template1"))
            break
        except OperationalError:
            if counter > 0:
                counter -= 1
                time.sleep(1)
            else:
                raise

    db_uri = CONN_FMT_STR.format(database=TEMPLATE_DB_NAME)

    if request.config.getoption("--alembic"):
        init_db_via_alembic(db_uri)
    else:
        init_db_via_create_all(db_uri)

    yield

    with temp_session(conn_str) as session:
        session.execute(text(f"DROP DATABASE {TEMPLATE_DB_NAME}"))


def init_db_via_create_all(db_uri: str) -> None:
    # dumb hack to easily get the create_all() functionality
    os.environ["SQLALCHEMY_DATABASE_URI"] = db_uri
    app = create_app()

    with app.app_context():
        db.session.commit()
        db.create_all()
        db.session.close()
        db.session.connection().connection.invalidate()  # type: ignore


def init_db_via_alembic(db_uri: str) -> None:
    # dumb hack to easily get the create_all() functionality
    os.environ["SQLALCHEMY_DATABASE_URI"] = db_uri
    app = create_app()
    with app.app_context():
        flask_migrate.upgrade()
        db.session.close()
        db.session.connection().connection.invalidate()  # type: ignore


@pytest.fixture()
def database(_db_template: None) -> str:
    """A clean Postgres database from the template with DDLs applied"""
    db_name = random_name(16)
    conn_str = CONN_FMT_STR.format(database="hushline")
    engine = create_engine(conn_str)
    engine = engine.execution_options(isolation_level="AUTOCOMMIT")

    session = sessionmaker(bind=engine)()

    sql = text(f"CREATE DATABASE {db_name} WITH TEMPLATE {TEMPLATE_DB_NAME}")
    session.execute(sql)

    # aggressively terminate all connections
    session.close()
    session.connection().connection.invalidate()
    engine.dispose()

    print(f"Postgres DB: {db_name}, template: {TEMPLATE_DB_NAME}")  # to help with debugging tests

    return db_name


@pytest.fixture(autouse=True)
def _insecure_scrypt_params(mocker: MockFixture) -> None:
    mocker.patch.dict(_SCRYPT_PARAMS, {"n": 2, "r": 1, "p": 1}, clear=True)


@pytest.fixture()
def app(database: str) -> Generator[Flask, None, None]:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    os.environ["SQLALCHEMY_DATABASE_URI"] = CONN_FMT_STR.format(database=database)

    # For premium tests
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_123"

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost:8080"
    app.config["PREFERRED_URL_SCHEME"] = "http"

    with app.app_context():
        db.create_all()

        # Create the default tiers
        # (this happens in the migrations, but migrations don't run in the tests)
        free_tier = Tier(name="Free", monthly_amount=0)
        business_tier = Tier(name="Business", monthly_amount=2000)
        business_tier.stripe_product_id = "prod_123"
        business_tier.stripe_price_id = "price_123"
        db.session.add(free_tier)
        db.session.add(business_tier)
        db.session.commit()

        yield app


@pytest.fixture()
def client(app: Flask) -> Generator[FlaskClient, None, None]:
    with app.test_client() as client:
        yield client


@pytest.fixture()
def user_password() -> str:
    return "Test-testtesttesttest-1"


@pytest.fixture()
def user(app: Flask, user_password: str, database: str) -> User:
    user = User(password=user_password)
    user.tier_id = 1
    db.session.add(user)
    db.session.flush()

    uuid_ish = str(uuid4())[0:12]
    username = Username(user_id=user.id, _username=f"test-{uuid_ish}", is_primary=True)
    db.session.add(username)
    db.session.commit()

    return user


@pytest.fixture()
def _authenticated_user(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True


@pytest.fixture()
def admin(app: Flask, user_password: str, database: str) -> User:
    user = User(password=user_password, is_admin=True)
    db.session.add(user)
    db.session.flush()

    uuid_ish = str(uuid4())[0:12]
    username = Username(user_id=user.id, _username=f"test-{uuid_ish}", is_primary=True)
    db.session.add(username)
    db.session.commit()

    return user


@pytest.fixture()
def _authenticated_admin(client: FlaskClient, admin: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = admin.id
        session["username"] = admin.primary_username.username
        session["is_authenticated"] = True


@pytest.fixture()
def _pgp_user(client: FlaskClient, user: User) -> None:
    with open("tests/test_pgp_key.txt") as f:
        user.pgp_key = f.read()
    db.session.commit()


@pytest.fixture()
def user_alias(app: Flask, user: User) -> Username:
    uuid_ish = str(uuid4())[0:12]
    username = Username(user_id=user.id, _username=f"test-{uuid_ish}", is_primary=False)
    db.session.add(username)
    db.session.commit()

    return username


@pytest.fixture()
def message(app: Flask, user: User) -> Message:
    msg = Message(content=str(uuid4()), username_id=user.primary_username.id)
    db.session.add(msg)
    db.session.commit()
    return msg
