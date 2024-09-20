import os
import random
import string
import time
from contextlib import contextmanager
from typing import Generator
from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from hushline import create_app
from hushline.db import db
from hushline.model import User, Username

CONN_FMT_STR = "postgresql+psycopg://hushline:hushline@postgres:5432/{database}"
TEMPLATE_DB_NAME = "app_db_template"


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
def _db_template() -> Generator[None, None, None]:
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


@pytest.fixture()
def app(database: str) -> Generator[Flask, None, None]:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    os.environ["SQLALCHEMY_DATABASE_URI"] = CONN_FMT_STR.format(database=database)

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SERVER_NAME"] = "localhost:8080"
    app.config["PREFERRED_URL_SCHEME"] = "http"

    with app.app_context():
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
def _pgp_user(client: FlaskClient, user: User) -> None:
    with open("tests/test_pgp_key.txt") as f:
        user.pgp_key = f.read()
    db.session.commit()
