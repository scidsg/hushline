import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from hushline.db import db

from ..helpers import (  # type: ignore[misc]
    Missing,
    format_param_dict,
    one_of,
    random_bool,
    random_optional_bool,
    random_optional_string,
    random_string,
)


@dataclass(frozen=True)
class OldSecondaryUser:
    id: int
    user_id: int
    username: str
    display_name: Optional[str]


@dataclass(frozen=True)
class OldMessage:
    id: int
    user_id: int
    secondary_user_id: Optional[int]
    content: str


@dataclass(frozen=True)
class OldUser:
    id: int
    primary_username: str
    display_name: Optional[str]
    bio: Optional[str]
    show_in_directory: Optional[bool]
    is_admin: bool
    is_verified: bool

    secondary_usernames: List[OldSecondaryUser]
    messages: List[OldMessage]

    extra_field_label1: Optional[str] = None
    extra_field_label2: Optional[str] = None
    extra_field_label3: Optional[str] = None
    extra_field_label4: Optional[str] = None

    extra_field_value1: Optional[str] = None
    extra_field_value2: Optional[str] = None
    extra_field_value3: Optional[str] = None
    extra_field_value4: Optional[str] = None

    extra_field_verified1: Optional[bool] = None
    extra_field_verified2: Optional[bool] = None
    extra_field_verified3: Optional[bool] = None
    extra_field_verified4: Optional[bool] = None


@dataclass(frozen=True)
class NewMessage:
    id: int
    username_id: int
    content: str


@dataclass(frozen=True)
class NewUsername:
    id: int
    user_id: int
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    show_in_directory: Optional[bool]
    is_primary: bool
    is_verified: bool

    messages: List[NewMessage]

    extra_field_label1: Optional[str] = None
    extra_field_label2: Optional[str] = None
    extra_field_label3: Optional[str] = None
    extra_field_label4: Optional[str] = None

    extra_field_value1: Optional[str] = None
    extra_field_value2: Optional[str] = None
    extra_field_value3: Optional[str] = None
    extra_field_value4: Optional[str] = None

    extra_field_verified1: Optional[bool] = None
    extra_field_verified2: Optional[bool] = None
    extra_field_verified3: Optional[bool] = None
    extra_field_verified4: Optional[bool] = None


@dataclass(frozen=True)
class NewUser:
    id: int
    is_admin: bool

    usernames: List[NewUsername]


class UpgradeTester:
    def __init__(self) -> None:
        self.old_users: List[OldUser] = []

    def load_data(self) -> None:
        for user_idx in range(12):
            user_params: Dict[str, Any] = {
                "primary_username": f"user_{random_string(10)}",
                "display_name": random_optional_string(10),
                "is_verified": random_bool(),
                "is_admin": random_bool(),
                "show_in_directory": random_bool(),
                "bio": random_optional_string(10),
            }

            for i in range(1, 5):
                if random_bool():
                    user_params[f"extra_field_label{i}"] = random_string(10)
                    user_params[f"extra_field_value{i}"] = random_string(10)
                    user_params[f"extra_field_verified{i}"] = random_optional_bool()

            columns, param_args = format_param_dict(user_params)
            result = list(
                db.session.execute(
                    db.text(
                        f"""
            INSERT INTO users (password_hash, {columns})
            VALUES ('$scrypt$', {param_args})
            RETURNING id
            """
                    ),
                    user_params,
                ),
            )

            user_id = result[0][0]
            secondary_usernames = []
            messages = []

            # make 0, 1, or 2 secondary usernames
            for second_idx in range(user_idx % 3):
                secondary_params: Dict[str, Any] = {
                    "user_id": user_id,
                    "username": random_string(10),
                    "display_name": random_optional_string(10),
                }
                columns, param_args = format_param_dict(secondary_params)
                result = list(
                    db.session.execute(
                        db.text(
                            f"""
                INSERT INTO secondary_usernames ({columns})
                VALUES ({param_args})
                RETURNING id
                """
                        ),
                        secondary_params,
                    )
                )
                secondary_usernames.append(OldSecondaryUser(id=result[0][0], **secondary_params))

            for _ in range(10):
                msg_params: Dict[str, Any] = {
                    "content": random_string(10),
                    "secondary_user_id": random.choice(secondary_usernames).id
                    if secondary_usernames and random_bool()
                    else None,
                }
                columns, param_args = format_param_dict(msg_params)
                result = list(
                    db.session.execute(
                        db.text(
                            f"""
                    INSERT INTO message (user_id, {columns})
                    VALUES (:user_id, {param_args})
                    RETURNING id
                    """
                        ),
                        params=dict(user_id=user_id, **msg_params),
                    )
                )
                messages.append(OldMessage(id=result[0][0], user_id=user_id, **msg_params))

            db.session.commit()
            self.old_users.append(
                OldUser(
                    id=user_id,
                    secondary_usernames=secondary_usernames,
                    messages=messages,
                    **user_params,
                )
            )

        assert self.old_users  # sensiblity check

    def check_upgrade(self) -> None:
        messages_by_username_id = defaultdict(list)
        results = db.session.execute(db.text("SELECT * FROM message"))
        for result in results:
            result_dict = result._asdict()
            msg = NewMessage(**result_dict)
            messages_by_username_id[msg.username_id].append(msg)

        usernames_by_user_id = defaultdict(list)
        results = db.session.execute(db.text("SELECT * FROM usernames"))
        for result in results:
            result_dict = result._asdict()
            username = NewUsername(
                **result_dict, messages=messages_by_username_id[result_dict["id"]]
            )
            usernames_by_user_id[username.user_id].append(username)

        new_users = []
        results = db.session.execute(db.text("SELECT id, is_admin FROM users"))
        for result in results:
            result_dict = result._asdict()
            user_id = result_dict["id"]

            messages = []
            for username in usernames_by_user_id[user_id]:
                messages.extend(messages_by_username_id[username.id])

            user = NewUser(
                id=user_id,
                is_admin=result_dict["is_admin"],
                usernames=usernames_by_user_id[user_id],
            )
            new_users.append(user)

        # sensible quick checks first:
        # users equal
        assert len(new_users) == len(self.old_users)
        # usernames = users + secondaries
        assert sum(len(x) for x in usernames_by_user_id.values()) == len(self.old_users) + sum(
            len(x.secondary_usernames) for x in self.old_users
        )
        # messages equal
        assert sum(len(y.messages) for x in new_users for y in x.usernames) == sum(
            len(x.messages) for x in self.old_users
        )

        for old_user in self.old_users:
            new_user = one_of(new_users, lambda x: x.id == old_user.id)
            new_username = one_of(usernames_by_user_id[old_user.id], lambda x: x.is_primary)
            assert new_username.user_id == old_user.id
            assert new_username.username == old_user.primary_username

            attrs = ["bio", "is_verified", "show_in_directory", "display_name"]
            for i in range(1, 5):
                attrs.append(f"extra_field_label{i}")
                attrs.append(f"extra_field_value{i}")
                attrs.append(f"extra_field_verified{i}")

            for attr in attrs:
                assert getattr(new_username, attr, Missing()) == getattr(old_user, attr, Missing())

            # check that all secondary usernames transferred
            new_secondaries = [x for x in usernames_by_user_id[old_user.id] if not x.is_primary]
            for old_secondary in old_user.secondary_usernames:
                new_secondary = one_of(
                    new_secondaries,
                    lambda x: x.username == old_secondary.username and not x.is_primary,
                )

                for attr in ["username", "display_name"]:
                    assert getattr(new_secondary, attr, Missing()) == getattr(
                        old_secondary, attr, Missing()
                    )

            # check that all messages updated correctly
            for old_message in old_user.messages:
                new_message_matches = [
                    y for x in new_user.usernames for y in x.messages if y.id == old_message.id
                ]
                assert len(new_message_matches) == 1
                new_message = new_message_matches[0]

                assert new_message.username_id in [x.id for x in new_user.usernames]
                assert new_message.content == old_message.content
                if old_message.secondary_user_id:
                    assert one_of(
                        old_user.secondary_usernames,
                        lambda x: x.id == old_message.secondary_user_id,
                    )


class DowngradeTester:
    def __init__(self) -> None:
        self.new_users: List[NewUser] = []

    def load_data(self) -> None:
        for user_idx in range(12):
            usernames = []

            user_params: Dict[str, Any] = {
                "is_admin": random_bool(),
            }

            columns, param_args = format_param_dict(user_params)
            result = list(
                db.session.execute(
                    db.text(
                        f"""
            INSERT INTO users (password_hash, {columns})
            VALUES ('$scrypt$', {param_args})
            RETURNING id
            """
                    ),
                    user_params,
                ),
            )

            user_id = result[0][0]

            # make 1 primary and 0, 1, or 2 aliases
            for username_idx in range(user_idx % 3 + 1):
                messages = []

                username_params: Dict[str, Any] = {
                    "user_id": user_id,
                    "username": random_string(20),
                    "display_name": random_optional_string(10),
                    "is_primary": username_idx == 0,
                    "is_verified": random_bool(),
                    "show_in_directory": random_bool(),
                    "bio": random_optional_string(10),
                }

                for i in range(1, 5):
                    if random_bool():
                        username_params[f"extra_field_label{i}"] = random_string(10)
                        username_params[f"extra_field_value{i}"] = random_string(10)
                        username_params[f"extra_field_verified{i}"] = random_optional_bool()

                columns, param_args = format_param_dict(username_params)
                result = list(
                    db.session.execute(
                        db.text(
                            f"""
                INSERT INTO usernames ({columns})
                VALUES ({param_args})
                RETURNING id
                """
                        ),
                        username_params,
                    ),
                )

                username_params.pop("user_id")
                username_id = result[0][0]

                for _ in range(5):
                    msg_params: Dict[str, Any] = {
                        "username_id": username_id,
                        "content": random_string(10),
                    }

                    columns, param_args = format_param_dict(msg_params)
                    result = list(
                        db.session.execute(
                            db.text(
                                f"""
                        INSERT INTO message ({columns})
                        VALUES ({param_args})
                        RETURNING id
                        """
                            ),
                            msg_params,
                        )
                    )

                    messages.append(
                        NewMessage(
                            id=result[0][0],
                            username_id=username_id,
                            content=msg_params["content"],
                        )
                    )

                usernames.append(
                    NewUsername(
                        id=username_id,
                        user_id=user_id,
                        **username_params,
                        messages=messages,
                    )
                )

            self.new_users.append(
                NewUser(
                    id=user_id,
                    is_admin=user_params["is_admin"],
                    usernames=usernames,
                ),
            )

        db.session.commit()

    def check_downgrade(self) -> None:
        assert self.new_users

        old_secondaries_by_user_id = defaultdict(list)
        results = db.session.execute(db.text("SELECT * FROM secondary_usernames"))
        for result in results:
            result_dict = result._asdict()
            old_secondaries_by_user_id[result_dict["user_id"]].append(
                OldSecondaryUser(**result_dict)
            )

        old_messages_by_user_id = defaultdict(list)
        results = db.session.execute(db.text("SELECT * FROM message"))
        for result in results:
            result_dict = result._asdict()
            old_messages_by_user_id[result_dict["user_id"]].append(OldMessage(**result_dict))

        old_users = []
        results = db.session.execute(db.text("SELECT * from users"))
        skip_keys = ["password_hash", "totp_secret", "email", "pgp_key"]
        for result in results:
            result_dict = {
                k: v
                for k, v in result._asdict().items()
                if k not in skip_keys and not k.startswith("smtp_")
            }
            old_users.append(
                OldUser(
                    secondary_usernames=old_secondaries_by_user_id[result_dict["id"]],
                    messages=old_messages_by_user_id[result_dict["id"]],
                    **result_dict,
                )
            )

        # sensibility checks first:
        # users equal
        assert len(old_users) == len(self.new_users)
        # users + secondaries = usernames
        assert len(old_users) + sum(len(x.secondary_usernames) for x in old_users) == sum(
            len(x.usernames) for x in self.new_users
        )
        # messages equal
        assert sum(len(x.messages) for x in old_users) == sum(
            len(y.messages) for x in self.new_users for y in x.usernames
        )

        for new_user in self.new_users:
            old_user = one_of(old_users, lambda x: x.id == new_user.id)

            for new_username in new_user.usernames:
                if new_username.is_primary:
                    # only primary usernames retain their fields
                    attrs = ["bio", "is_verified", "show_in_directory", "display_name"]
                    for i in range(1, 5):
                        attrs.append(f"extra_field_label{i}")
                        attrs.append(f"extra_field_value{i}")
                        attrs.append(f"extra_field_verified{i}")

                    for attr in attrs:
                        assert getattr(old_user, attr, Missing()) == getattr(
                            new_username, attr, Missing()
                        )
                else:
                    # only secondary usernames will have a match in the downgraded
                    # secondary_usernames table
                    old_secondary = one_of(
                        old_user.secondary_usernames, lambda x: x.username == new_username.username
                    )
                    assert old_secondary.user_id == new_username.user_id
                    assert old_secondary.display_name == new_username.display_name

                for new_msg in new_username.messages:
                    old_msg = one_of(old_user.messages, lambda x: x.id == new_msg.id)
                    assert old_msg.content == new_msg.content
                    assert old_msg.user_id == old_user.id

                    if new_username.is_primary:
                        assert old_msg.secondary_user_id is None
                    else:
                        # inserts back into the secondary_usernames table aren't deterministic,
                        # so we can't rely on user_id's being equal. only usernames.
                        assert (
                            len(
                                [
                                    y.username
                                    for x in self.new_users
                                    for y in x.usernames
                                    if y.username == old_secondary.username
                                ]
                            )
                            == 1
                        )
