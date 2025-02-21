from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class OrganizationSetting(Model):
    __tablename__ = "organization_settings"

    # keys
    BRAND_LOGO = "brand_logo"
    BRAND_NAME = "brand_name"
    BRAND_PRIMARY_COLOR = "brand_primary_color"
    BRAND_PROFILE_HEADER_TEMPLATE = "brand_profile_header_template"
    DIRECTORY_INTRO_TEXT = "directory_intro_text"
    GUIDANCE_ENABLED = "guidance_enabled"
    GUIDANCE_EXIT_BUTTON_TEXT = "guidance_exit_button_text"
    GUIDANCE_EXIT_BUTTON_LINK = "guidance_exit_button_link"
    GUIDANCE_PROMPTS = "guidance_prompts"
    HIDE_DONATE_BUTTON = "hide_donate_button"
    HOMEPAGE_USER_NAME = "homepage_user_name"

    # non-default values
    BRAND_LOGO_VALUE = "brand/logo.png"

    _DEFAULT_VALUES: dict[str, Any] = {
        BRAND_NAME: "🤫 Hush Line",
        BRAND_PRIMARY_COLOR: "#7d25c1",
        BRAND_PROFILE_HEADER_TEMPLATE: "Submit message to {{ display_name_or_username }}",
        GUIDANCE_ENABLED: False,
        GUIDANCE_EXIT_BUTTON_TEXT: "Leave",
        GUIDANCE_EXIT_BUTTON_LINK: "https://en.wikipedia.org/wiki/Main_Page",
        GUIDANCE_PROMPTS: [{"heading_text": "", "prompt_text": "", "index": 0}],
        HIDE_DONATE_BUTTON: False,
    }

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[JSON] = mapped_column(type_=JSONB)

    @classmethod
    def upsert(cls, key: str, value: Any) -> None:
        db.session.execute(
            insert(OrganizationSetting)
            .values(key=key, value=value)
            .on_conflict_do_update(
                constraint=f"pk_{cls.__tablename__}",
                set_={"value": value},
            )
        )

    @classmethod
    def fetch(cls, *keys: str) -> dict[str, Any]:
        rows = db.session.scalars(
            db.select(OrganizationSetting).filter(OrganizationSetting.key.in_(keys))
        ).all()

        results = {key: cls._DEFAULT_VALUES.get(key) for key in keys}
        for row in rows:
            results[row.key] = row.value

        return results

    @classmethod
    def fetch_one(cls, key: str) -> Any:
        result = db.session.scalars(db.select(OrganizationSetting).filter_by(key=key)).one_or_none()
        if not result:
            return cls._DEFAULT_VALUES.get(key)
        return result.value
