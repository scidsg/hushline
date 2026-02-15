import logging

from flask import (
    Flask,
    render_template,
)
from werkzeug.wrappers.response import Response

from hushline.routes.auth import register_auth_routes
from hushline.routes.common import get_ip_address
from hushline.routes.directory import register_directory_routes
from hushline.routes.email_headers import register_email_headers_routes
from hushline.routes.forms import (  # noqa: F401
    DynamicMessageForm,
    LoginForm,
    RegistrationForm,
    TwoFactorForm,
)
from hushline.routes.inbox import register_inbox_routes
from hushline.routes.index import register_index_routes
from hushline.routes.message import register_message_routes
from hushline.routes.onboarding import register_onboarding_routes
from hushline.routes.profile import register_profile_routes
from hushline.routes.vision import register_vision_routes

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


def init_app(app: Flask) -> None:
    register_auth_routes(app)
    register_index_routes(app)
    register_inbox_routes(app)
    register_profile_routes(app)
    register_message_routes(app)
    register_onboarding_routes(app)
    register_directory_routes(app)
    register_vision_routes(app)
    register_email_headers_routes(app)

    @app.route("/info")
    def server_info() -> Response | str:
        return render_template("server_info.html", ip_address=get_ip_address())

    @app.route("/health.json")
    def health() -> dict[str, str]:
        return {"status": "ok"}
