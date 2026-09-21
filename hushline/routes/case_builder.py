from flask import Flask, current_app, make_response, url_for
from werkzeug.wrappers.response import Response

from hushline.model import OrganizationSetting


def register_case_builder_routes(app: Flask) -> None:
    @app.get("/case-builder")
    def case_builder() -> Response:
        brand_name = OrganizationSetting.fetch_one(OrganizationSetting.BRAND_NAME) or "Hush Line"
        # Avoid the shared context processors: they read account and session state that this
        # account-independent workspace does not need.
        template = current_app.jinja_env.get_template("case_builder.html")
        response = make_response(
            template.render(
                brand_name=brand_name,
                case_builder_script_url=url_for(
                    "static", filename="js/case-builder.js", v="case-builder-2"
                ),
                stylesheet_url=url_for("static", filename="css/style.css", v="case-builder-2"),
                leave_url=url_for("directory"),
            )
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
