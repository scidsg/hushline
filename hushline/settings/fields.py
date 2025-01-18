from typing import Tuple

from flask import (
    Blueprint,
    current_app,
    flash,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import FieldDefinition, FieldType, User
from hushline.settings.forms import FieldForm
from hushline.utils import redirect_to_self


def register_fields_routes(bp: Blueprint) -> None:
    @bp.route("/fields", methods=["GET", "POST"])
    @authentication_required
    def fields() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        username = user.primary_username

        if username is None:
            raise Exception("Username not found")

        if request.method == "POST":
            field_form = FieldForm()
            if field_form.validate():
                current_app.logger.info(f"Field form validated: {field_form.data}")

                # Create a new field
                if field_form.submit.name in request.form:
                    current_app.logger.info("Adding new field")
                    field_definition = FieldDefinition(
                        username,
                        field_form.label.data,
                        FieldType(field_form.field_type.data),
                        field_form.required.data,
                        field_form.enabled.data,
                        field_form.encrypted.data,
                        field_form.choices.data,
                    )
                    db.session.add(field_definition)
                    db.session.commit()
                    flash("New field added.")
                    return redirect_to_self()

                # Update an existing field
                if "update_field" in request.form:
                    pass

                # Delete a field
                if "delete_field" in request.form:
                    pass

                # Move a field up
                if "move_up" in request.form:
                    pass

                # Move a field down
                if "move_down" in request.form:
                    pass

        field_forms = [
            FieldForm(
                id=field.id,
                label=field.label,
                field_type=field.field_type,
                choices=field.choices,
                encrypted=field.encrypted,
                required=field.required,
                enabled=field.enabled,
            )
            for field in username.message_fields
        ]

        new_field_form = FieldForm()

        return render_template(
            "settings/fields.html",
            field_forms=field_forms,
            new_field_form=new_field_form,
        ), 200
