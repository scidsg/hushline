from typing import Generator

import pytest
from cryptography.fernet import Fernet
from flask import Flask, request, session, url_for
from flask.testing import FlaskClient

from hushline.secure_session import EncryptedSessionInterface

FERNET_KEY = Fernet.generate_key().decode("utf-8")
ARG_KEY = "x"
SESSION_KEY = "y"
MISSING = "missing"


class Fixtures:
    HAS_SESSION_KEY = True

    @pytest.fixture()
    def app(self) -> Generator[Flask, None, None]:
        app_ = Flask(__name__)
        if self.HAS_SESSION_KEY:
            app_.config["SESSION_FERNET_KEY"] = FERNET_KEY
        app_.config["SERVER_NAME"] = "localhost.tld"
        app_.session_interface = EncryptedSessionInterface()

        @app_.route("/session", methods=["GET", "POST", "DELETE"])
        def has_session() -> str:
            if request.method == "POST":
                session[SESSION_KEY] = request.args[ARG_KEY]
            elif request.method == "DELETE":
                del session[SESSION_KEY]
            return session.get(SESSION_KEY, MISSING)

        @app_.route("/contains")
        def contains_session_key() -> str:
            return str(SESSION_KEY in session)

        @app_.route("/length")
        def session_length() -> str:
            return str(len(session))

        @app_.route("/no-session", methods=["GET", "POST"])
        def no_session() -> str:
            return ""

        with app_.app_context():
            yield app_

    @pytest.fixture()
    def client(self, app: Flask) -> Generator[FlaskClient, None, None]:
        with app.test_client() as c:
            yield c


class TestSessionEnabled(Fixtures):
    def test_get_set(self, client: FlaskClient) -> None:
        resp = client.get(url_for("has_session"))
        assert resp.status_code == 200
        assert resp.text == MISSING

    def test_key_only_session_access_sets_vary_cookie(self, client: FlaskClient) -> None:
        resp = client.post(url_for("has_session", **{ARG_KEY: "value"}))  # type: ignore[arg-type]
        assert resp.status_code == 200

        contains_resp = client.get(url_for("contains_session_key"))
        assert contains_resp.status_code == 200
        assert contains_resp.text == "True"
        assert "Cookie" in contains_resp.vary

        length_resp = client.get(url_for("session_length"))
        assert length_resp.status_code == 200
        assert length_resp.text == "1"
        assert "Cookie" in length_resp.vary

        expected = "test data"
        resp = client.post(url_for("has_session", **{ARG_KEY: expected}))  # type: ignore[arg-type]
        assert resp.status_code == 200
        assert resp.text == expected

        resp = client.get(url_for("has_session"))
        assert resp.status_code == 200
        assert resp.text == expected

        resp = client.delete(url_for("has_session"))
        assert resp.status_code == 200
        assert resp.text == MISSING

        resp = client.get(url_for("has_session"))
        assert resp.status_code == 200
        assert resp.text == MISSING


class TestNoSessionEnabled(Fixtures):
    HAS_SESSION_KEY = False

    def test_no_session(self, client: FlaskClient) -> None:
        resp = client.get(url_for("no_session"))
        assert resp.status_code == 200
