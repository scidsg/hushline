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
                if field_form.update.name in request.form:
                    current_app.logger.info("Updating field")
                    field_definition = db.session.scalars(
                        db.select(FieldDefinition).filter_by(id=int(field_form.id.data))
                    ).one()
                    field_definition.label = field_form.label.data
                    field_definition.field_type = FieldType(field_form.field_type.data)
                    field_definition.required = field_form.required.data
                    field_definition.enabled = field_form.enabled.data
                    field_definition.encrypted = field_form.encrypted.data
                    field_definition.choices = field_form.choices.data
                    db.session.commit()
                    flash("Field updated.")
                    return redirect_to_self()

                # Delete a field
                if field_form.delete.name in request.form:
                    current_app.logger.info("Deleting field")
                    field_definition = db.session.scalars(
                        db.select(FieldDefinition).filter_by(id=int(field_form.id.data))
                    ).one()
                    db.session.delete(field_definition)
                    db.session.commit()
                    flash("Field deleted.")
                    return redirect_to_self()

                # Move a field up
                if field_form.move_up.name in request.form:
                    current_app.logger.info("Moving field up")
                    field_definition = db.session.scalars(
                        db.select(FieldDefinition).filter_by(id=int(field_form.id.data))
                    ).one()
                    field_definition.move_up()
                    flash("Field moved up.")
                    return redirect_to_self()

                # Move a field down
                if field_form.move_down.name in request.form:
                    current_app.logger.info("Moving field down")
                    field_definition = db.session.scalars(
                        db.select(FieldDefinition).filter_by(id=int(field_form.id.data))
                    ).one()
                    field_definition.move_down()
                    flash("Field moved down.")
                    return redirect_to_self()

        field_forms = []
        for field in username.message_fields:
            form = FieldForm(obj=field)
            form.field_type.data = field.field_type.value
            field_forms.append(form)

        new_field_form = FieldForm()

        return render_template(
            "settings/fields.html",
            field_forms=field_forms,
            new_field_form=new_field_form,
        ), 200
