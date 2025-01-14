import json
from typing import Tuple

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import (
    OrganizationSetting,
    User,
)
from hushline.settings.common import (
    form_error,
)
from hushline.settings.forms import (
    UserGuidanceAddPromptForm,
    UserGuidanceEmergencyExitForm,
    UserGuidanceForm,
    UserGuidancePromptContentForm,
)


def register_guidance_routes(bp: Blueprint) -> None:
    @bp.route("/guidance", methods=["GET", "POST"])
    @admin_authentication_required
    def guidance() -> Tuple[str, int] | Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        show_user_guidance = OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_ENABLED)

        user_guidance_form = UserGuidanceForm(show_user_guidance=show_user_guidance)
        user_guidance_emergency_exit_form = UserGuidanceEmergencyExitForm(
            exit_button_text=OrganizationSetting.fetch_one(
                OrganizationSetting.GUIDANCE_EXIT_BUTTON_TEXT
            ),
            exit_button_link=OrganizationSetting.fetch_one(
                OrganizationSetting.GUIDANCE_EXIT_BUTTON_LINK
            ),
        )

        guidance_prompt_values = OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_PROMPTS)
        if guidance_prompt_values is None:
            guidance_prompt_values = []
        user_guidance_prompt_forms = [
            UserGuidancePromptContentForm(
                heading_text=guidance_prompt_values[i].get("heading_text", ""),
                prompt_text=guidance_prompt_values[i].get("prompt_text", ""),
            )
            for i in range(len(guidance_prompt_values))
        ]

        user_guidance_add_prompt_form = UserGuidanceAddPromptForm()

        status_code = 200
        if request.method == "POST":
            # Show user guidance form
            if (user_guidance_form.submit.name in request.form) and user_guidance_form.validate():
                OrganizationSetting.upsert(
                    key=OrganizationSetting.GUIDANCE_ENABLED,
                    value=user_guidance_form.show_user_guidance.data,
                )
                db.session.commit()
                if user_guidance_form.show_user_guidance.data:
                    show_user_guidance = True
                    flash("👍 User guidance enabled.")
                else:
                    show_user_guidance = False
                    flash("👍 User guidance disabled.")
                return redirect(url_for(".guidance"))

            # Emergency exit form
            elif (
                user_guidance_emergency_exit_form.submit.name in request.form
            ) and user_guidance_emergency_exit_form.validate():
                OrganizationSetting.upsert(
                    key=OrganizationSetting.GUIDANCE_EXIT_BUTTON_TEXT,
                    value=user_guidance_emergency_exit_form.exit_button_text.data,
                )
                OrganizationSetting.upsert(
                    key=OrganizationSetting.GUIDANCE_EXIT_BUTTON_LINK,
                    value=user_guidance_emergency_exit_form.exit_button_link.data,
                )
                db.session.commit()
                flash("👍 Emergency exit button updated successfully.")
                return redirect(url_for(".guidance"))

            # Add prompt form
            elif (
                user_guidance_add_prompt_form.submit.name in request.form
            ) and user_guidance_add_prompt_form.validate():
                new_prompt_value = {
                    "heading_text": "",
                    "prompt_text": "",
                }
                guidance_prompt_values.append(new_prompt_value)
                user_guidance_prompt_forms.append(UserGuidancePromptContentForm())

                OrganizationSetting.upsert(
                    key=OrganizationSetting.GUIDANCE_PROMPTS,
                    value=guidance_prompt_values,
                )
                db.session.commit()
                flash("👍 Prompt added.")
                return redirect(url_for(".guidance"))

            # Guidance prompt forms
            else:
                # Since we have an unknown number of prompt forms, we need to loop through them and
                # see which if any were submitted. We handle the case where an invalid form is
                # submitted at the end, after we conclude that none of these forms were submitted.
                form_submitted = False
                for i, form in enumerate(user_guidance_prompt_forms):
                    if (
                        request.form.get("index") == str(i)
                        and (
                            form.submit.name in request.form
                            or form.delete_submit.name in request.form
                        )
                        and form.validate()
                    ):
                        form_submitted = True

                        # Update
                        if form.submit.name in request.form:
                            guidance_prompt_values[i] = {
                                "heading_text": form.heading_text.data,
                                "prompt_text": form.prompt_text.data,
                                "index": i,
                            }
                            flash("👍 Prompt updated.")

                        # Delete
                        elif form.delete_submit.name in request.form:
                            guidance_prompt_values.pop(i)
                            user_guidance_prompt_forms.pop(i)
                            flash("👍 Prompt deleted.")

                        # Save the updated values
                        OrganizationSetting.upsert(
                            key=OrganizationSetting.GUIDANCE_PROMPTS,
                            value=guidance_prompt_values,
                        )
                        db.session.commit()
                        return redirect(url_for(".guidance"))

                # Invalid form?
                if not form_submitted:
                    current_app.logger.debug(json.dumps(form.errors, indent=2))

                    form_error()
                    status_code = 400

        return render_template(
            "settings/guidance.html",
            user=user,
            user_guidance_form=user_guidance_form,
            user_guidance_emergency_exit_form=user_guidance_emergency_exit_form,
            user_guidance_prompt_forms=user_guidance_prompt_forms,
            user_guidance_add_prompt_form=user_guidance_add_prompt_form,
            show_user_guidance=show_user_guidance,
        ), status_code
