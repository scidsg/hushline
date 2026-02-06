from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generator, Optional, Sequence

from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class Username(Model):
    """
    Class representing a username and associated profile.
    This was pulled out of the `User` class so that a `username` could be globally unique among
    both users and aliases and enforced at the database level.
    """

    __tablename__ = "usernames"
    __table_args__ = (
        db.Index(
            "uq_usernames_username_lower",
            db.func.lower("username"),
            unique=True,
        ),
    )

    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 25
    DISPLAY_NAME_MIN_LENGTH = 1
    DISPLAY_NAME_MAX_LENGTH = 100

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship()
    _username: Mapped[str] = mapped_column("username", unique=True)
    _display_name: Mapped[Optional[str]] = mapped_column("display_name", db.String(80))
    is_primary: Mapped[bool] = mapped_column()
    is_verified: Mapped[bool] = mapped_column(default=False)
    show_in_directory: Mapped[bool] = mapped_column(default=False)
    bio: Mapped[Optional[str]] = mapped_column(db.Text)

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
        return [x for x in self.extra_fields if x.label and x.value]

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
