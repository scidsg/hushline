from flask import Flask, url_for


def test_login(app: Flask) -> None:
    with app.test_client() as client:
        resp = client.get(url_for("login"))
    assert resp.status_code == 200
