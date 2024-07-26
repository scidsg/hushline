from flask import Flask


def test_info_available_on_personal_server(app: Flask) -> None:
    app.config["IS_PERSONAL_SERVER"] = True
    app.config["ONION_HOSTNAME"] = "example.onion"

    with app.test_client() as client:
        response = client.get("/info")
        assert response.status_code == 200
        assert "Hush Line Personal Server" in response.get_data(as_text=True)
        assert "example.onion" in response.get_data(as_text=True)


def test_info_not_available_by_default(app: Flask) -> None:
    app.config["IS_PERSONAL_SERVER"] = False
    app.config["ONION_HOSTNAME"] = "example.onion"

    with app.test_client() as client:
        response = client.get("/info")
        print(response.get_data(as_text=True))
        assert response.status_code == 404
