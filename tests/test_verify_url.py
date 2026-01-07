import multiprocessing
import socket
import time
import traceback
import urllib.parse
from typing import Generator

import aiohttp
import pytest
import requests
from flask import Flask, request, url_for
from flask.testing import FlaskClient
from markupsafe import Markup

from hushline.db import db
from hushline.model import User
from hushline.settings.common import create_profile_forms, verify_url
from tests.helpers import form_to_data

app = Flask(__name__)

HOSTNAME = socket.gethostname()


@app.route("/")
def index() -> str:
    if profile := request.args.get("profile"):
        url = Markup.escape(profile)
        return f"""<html><body><a href="{url}" rel="me"></body></html>"""
    else:
        return "<html><body></body></html>"


def unused_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_verification_app(port: int) -> None:
    print(f"Binding app to port {port}")
    try:
        app.run(host=HOSTNAME, port=port, debug=False)
    except Exception as e:
        print(f"App failed to start: {e}")
        print(traceback.format_exc())
        raise e


def await_verification_app(port: int) -> None:
    for _ in range(10):
        try:
            resp = requests.get(f"http://{HOSTNAME}:{port}/", timeout=0.05)
            resp.raise_for_status()
            return
        except requests.exceptions.ConnectionError as e:
            print(f"Could not reach port {port}: {e}")
            time.sleep(0.5)
    raise Exception("App could not be reached")


@pytest.mark.local_only()
@pytest.fixture(scope="module")
def verification_server() -> Generator[int, None, None]:
    port = unused_port()

    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=start_verification_app, args=(port,))
    proc.start()
    await_verification_app(port)

    yield port

    proc.kill()
    proc.join()


@pytest.mark.local_only()
@pytest.mark.asyncio()
async def test_verify_url(user: User, verification_server: int) -> None:
    username = user.primary_username
    assert username.extra_field_verified1 is False  # precondition

    profile_url = url_for("profile", username=username.username, _external=True)
    encoded_url = urllib.parse.quote(profile_url)
    url_to_verify = f"http://{HOSTNAME}:{verification_server}/?profile={encoded_url}"

    async with aiohttp.ClientSession() as sess:
        await verify_url(sess, username, 1, url_to_verify, profile_url)
    db.session.commit()

    db.session.refresh(username)
    assert username.extra_field_verified1 is True


@pytest.mark.local_only()
@pytest.mark.asyncio()
async def test_verify_url_fail(user: User, verification_server: int) -> None:
    username = user.primary_username
    username.extra_field_verified1 = True

    profile_url = url_for("profile", username=username.username, _external=True)
    url_to_verify = f"http://{HOSTNAME}:{verification_server}/"

    async with aiohttp.ClientSession() as sess:
        await verify_url(sess, username, 1, url_to_verify, profile_url)
    db.session.commit()

    db.session.refresh(username)
    assert username.extra_field_verified1 is False


@pytest.mark.local_only()
@pytest.mark.usefixtures("_authenticated_user")
def test_verify_url_request(client: FlaskClient, user: User, verification_server: int) -> None:
    assert user.primary_username.extra_field_verified1 is False  # precondition

    label = "foo"
    profile_url = url_for("profile", username=user.primary_username.username, _external=True)
    value = f"http://{HOSTNAME}:{verification_server}/?profile={profile_url}"

    _, _, profile_form = create_profile_forms(user.primary_username)
    profile_form.extra_field_label1.data = label
    profile_form.extra_field_value1.data = value

    resp = client.post(
        url_for("settings.profile"),
        data=form_to_data(profile_form),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Bio and fields updated successfully" in resp.text, resp.text

    db.session.refresh(user.primary_username)
    assert user.primary_username.extra_field_label1 == label
    assert user.primary_username.extra_field_value1 == value
    assert user.primary_username.extra_field_verified1 is True


@pytest.mark.local_only()
@pytest.mark.usefixtures("_authenticated_user")
def test_verify_url_request_fail(client: FlaskClient, user: User, verification_server: int) -> None:
    user.primary_username.extra_field_verified1 = True
    db.session.commit()

    label = "foo"
    value = f"http://{HOSTNAME}:{verification_server}/"

    _, _, profile_form = create_profile_forms(user.primary_username)
    profile_form.extra_field_label1.data = label
    profile_form.extra_field_value1.data = value

    resp = client.post(
        url_for("settings.profile"),
        data=form_to_data(profile_form),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Bio and fields updated successfully" in resp.text

    db.session.refresh(user.primary_username)
    assert user.primary_username.extra_field_label1 == label
    assert user.primary_username.extra_field_value1 == value
    assert user.primary_username.extra_field_verified1 is False


@pytest.mark.asyncio()
async def test_verify_url_blocks_private_ip_in_production(app: Flask, user: User) -> None:
    username = user.primary_username
    username.extra_field_verified1 = True

    profile_url = url_for("profile", username=username.username, _external=True)
    url_to_verify = "https://127.0.0.1/"

    original_testing = app.config["TESTING"]
    app.config["TESTING"] = False
    try:
        async with aiohttp.ClientSession() as sess:
            await verify_url(sess, username, 1, url_to_verify, profile_url)
    finally:
        app.config["TESTING"] = original_testing

    db.session.commit()
    db.session.refresh(username)
    assert username.extra_field_verified1 is False


@pytest.mark.asyncio()
async def test_verify_url_blocks_localhost_in_production(app: Flask, user: User) -> None:
    username = user.primary_username
    username.extra_field_verified1 = True

    profile_url = url_for("profile", username=username.username, _external=True)
    url_to_verify = "https://localhost/"

    original_testing = app.config["TESTING"]
    app.config["TESTING"] = False
    try:
        async with aiohttp.ClientSession() as sess:
            await verify_url(sess, username, 1, url_to_verify, profile_url)
    finally:
        app.config["TESTING"] = original_testing

    db.session.commit()
    db.session.refresh(username)
    assert username.extra_field_verified1 is False
