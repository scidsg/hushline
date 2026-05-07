from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generator, Optional, Sequence
from urllib.parse import urlsplit

from sqlalchemy import Index, func, literal_column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from hushline.db import db
from hushline.model import FieldDefinition, FieldType

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model import User
else:
    Model = db.Model


@dataclass(frozen=True, repr=False, eq=False)
class ExtraField:
    label: Optional[str]
    value: Optional[str]
    is_verified: Optional[bool]


def normalize_embed_origin(origin: str) -> str:
    stripped_origin = origin.strip()
    parsed = urlsplit(stripped_origin)
    if (
        not stripped_origin
        or stripped_origin != origin
        or "*" in stripped_origin
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise ValueError("Embed origins must be exact http(s) origins without paths or wildcards.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Embed origins must include a valid port when a port is specified."
        ) from exc

    host = parsed.hostname.lower()
    if "*" in host:
        raise ValueError("Embed origins cannot contain wildcards.")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    scheme = parsed.scheme.lower()
    normalized_origin = f"{scheme}://{host}"
    default_port = 443 if scheme == "https" else 80
    if port is not None and port != default_port:
        normalized_origin = f"{normalized_origin}:{port}"
    return normalized_origin


class Username(Model):
    """
    Class representing a username and associated profile.
    This was pulled out of the `User` class so that a `username` could be globally unique among
    both users and aliases and enforced at the database level.
    """

    __tablename__ = "usernames"
    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 25
    DISPLAY_NAME_MIN_LENGTH = 1
    DISPLAY_NAME_MAX_LENGTH = 80
    BIO_MAX_LENGTH = 250
    EXTRA_FIELD_LABEL_MAX_LENGTH = 50
    EXTRA_FIELD_VALUE_MAX_LENGTH = 4096

    __table_args__ = (
        Index("uq_usernames_username_lower", func.lower(literal_column("username")), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship()
    _username: Mapped[str] = mapped_column("username", unique=True)
    _display_name: Mapped[Optional[str]] = mapped_column(
        "display_name", db.String(DISPLAY_NAME_MAX_LENGTH)
    )
    is_primary: Mapped[bool] = mapped_column()
    is_verified: Mapped[bool] = mapped_column(default=False)
    show_in_directory: Mapped[bool] = mapped_column(default=False)
    bio: Mapped[Optional[str]] = mapped_column(db.Text)
    embed_enabled: Mapped[bool] = mapped_column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    embed_admin_disabled: Mapped[bool] = mapped_column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    embed_allowed_origins: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    # Extra fields
    extra_field_label1: Mapped[Optional[str]]
    extra_field_value1: Mapped[Optional[str]]
    extra_field_label2: Mapped[Optional[str]]
    extra_field_value2: Mapped[Optional[str]]
    extra_field_label3: Mapped[Optional[str]]
    extra_field_value3: Mapped[Optional[str]]
    extra_field_label4: Mapped[Optional[str]]
    extra_field_value4: Mapped[Optional[str]]
    extra_field_verified1: Mapped[Optional[bool]] = mapped_column(default=False)
    extra_field_verified2: Mapped[Optional[bool]] = mapped_column(default=False)
    extra_field_verified3: Mapped[Optional[bool]] = mapped_column(default=False)
    extra_field_verified4: Mapped[Optional[bool]] = mapped_column(default=False)

    message_fields: Mapped[list["FieldDefinition"]] = relationship(
        back_populates="username",
        order_by="FieldDefinition.sort_order",
    )

    def __init__(
        self,
        _username: str,
        is_primary: bool,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            _username=_username,  # type: ignore[call-arg]
            is_primary=is_primary,  # type: ignore[call-arg]
            **kwargs,
        )

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        self._username = username
        self.is_verified = False

    @property
    def display_name(self) -> Optional[str]:
        return self._display_name

    @display_name.setter
    def display_name(self, display_name: str | None) -> None:
        self._display_name = display_name
        self.is_verified = False

    @property
    def extra_fields(self) -> Generator[ExtraField, None, None]:
        for i in range(1, 5):
            yield ExtraField(
                getattr(self, f"extra_field_label{i}", None),
                getattr(self, f"extra_field_value{i}", None),
                getattr(self, f"extra_field_verified{i}", None),
            )

    @property
    def valid_fields(self) -> Sequence[ExtraField]:
        valid_fields = [x for x in self.extra_fields if x.label and x.value]
        profile_fields: list[ExtraField] = []
        if account_category := self.user.account_category_label:
            profile_fields.append(ExtraField("Category", account_category, False))
        if profile_location := self.user.profile_location:
            profile_fields.append(ExtraField("Location", profile_location, False))
        return [*profile_fields, *valid_fields]

    @validates("embed_allowed_origins")
    def validate_embed_allowed_origins(self, _key: str, origins: Sequence[str] | None) -> list[str]:
        return self.normalize_embed_allowed_origins(origins or [])

    @staticmethod
    def normalize_embed_allowed_origins(origins: Sequence[str]) -> list[str]:
        normalized_origins: list[str] = []
        for origin in origins:
            normalized_origin = normalize_embed_origin(origin)
            if normalized_origin not in normalized_origins:
                normalized_origins.append(normalized_origin)
        return normalized_origins

    def set_embed_allowed_origins(self, origins: Sequence[str]) -> None:
        self.embed_allowed_origins = self.normalize_embed_allowed_origins(origins)

    @property
    def embed_owner_has_required_plan(self) -> bool:
        return self.user.is_current_paid_super_user

    @property
    def embed_owner_has_required_key(self) -> bool:
        return not self.user.is_suspended and bool(self.user.message_encryption_target)

    @property
    def embed_owner_is_eligible(self) -> bool:
        return self.embed_owner_has_required_plan and self.embed_owner_has_required_key

    @property
    def embed_is_eligible(self) -> bool:
        from hushline.model.organization_setting import OrganizationSetting

        return (
            bool(OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED))
            and self.embed_enabled
            and not self.embed_admin_disabled
            and bool(self.embed_allowed_origins)
            and self.embed_owner_is_eligible
        )

    def embed_allows_origin(self, origin: str) -> bool:
        if not self.embed_is_eligible:
            return False
        try:
            normalized_origin = normalize_embed_origin(origin)
            allowed_origins = self.normalize_embed_allowed_origins(self.embed_allowed_origins or [])
        except ValueError:
            return False
        return normalized_origin in allowed_origins

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} username={self.username}>"

    def create_default_field_defs(self) -> None:
        """
        If there are no message fields, create the default ones.
        """
        if not self.message_fields:
            db.session.add(
                FieldDefinition(
                    self,
                    "Contact Method",
                    FieldType.TEXT,
                    False,
                    True,
                    True,
                    [],
                )
            )
            db.session.add(
                FieldDefinition(
                    self,
                    "Message",
                    FieldType.MULTILINE_TEXT,
                    True,
                    True,
                    True,
                    [],
                )
            )
            db.session.commit()
