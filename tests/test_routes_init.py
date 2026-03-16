from unittest.mock import patch

from flask import Flask
from flask.testing import FlaskClient


def test_info_route_renders_server_ip(app: Flask) -> None:
    with (
        app.test_request_context("/info"),
        patch("hushline.routes.get_ip_address", return_value="203.0.113.10") as get_ip_address,
        patch("hushline.routes.render_template", return_value="rendered") as render_template,
    ):
        response = app.view_functions["server_info"]()

    assert response == "rendered"
    get_ip_address.assert_called_once_with()
    render_template.assert_called_once_with(
        "server_info.html",
        ip_address="203.0.113.10",
    )


def test_health_json_route_returns_ok(client: FlaskClient) -> None:
    response = client.get("/health.json")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}
