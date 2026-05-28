import ast
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet, InvalidToken
from pytest_mock import MockFixture
from sqlalchemy import select

from hushline.config import ENCRYPTED_FIELD_WRITE_FORMAT, EncryptedFieldWriteFormat
from hushline.crypto import (
    ENCRYPTED_FIELD_CONTRACT_BY_ID,
    ENCRYPTED_FIELD_CONTRACTS,
    ENCRYPTED_FIELD_ENVELOPE_PREFIX,
    ENCRYPTED_FIELD_LEGACY_MAX_LENGTH,
    ENCRYPTED_FIELD_MUTABLE_AAD_NAMES,
    parse_encrypted_field_aead_envelope,
    parse_encrypted_field_envelope,
    serialize_encrypted_field_envelope,
)
from hushline.db import db
from hushline.model import (
    FieldDefinition,
    FieldType,
    FieldValue,
    Message,
    NotificationRecipient,
    User,
)

LEGACY_FERNET_KEY = "jY0gDbATEOQolx2SGj46YnkkbN6HQBB4YCABzwl1H1A="
PGP_CIPHERTEXT = (
    "-----BEGIN PGP MESSAGE-----\n\n"
    "legacy encrypted custom field value\n"
    "-----END PGP MESSAGE-----"
)
LONG_EMAIL = f"{'u' * 64}@" f"{'d' * 63}." f"{'e' * 63}." f"{'f' * 61}"
LONG_PGP_BLOCK = (
    "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n" f"{'a' * 512}\n" "-----END PGP PUBLIC KEY BLOCK-----"
)
LONG_PGP_CIPHERTEXT = "-----BEGIN PGP MESSAGE-----\n\n" f"{'b' * 512}\n" "-----END PGP MESSAGE-----"


@pytest.fixture()
def env_var_modifier() -> Callable[[MockFixture], None]:
    def apply(mocker: MockFixture) -> None:
        mocker.patch.dict(os.environ, {"ENCRYPTION_KEY": LEGACY_FERNET_KEY})

    return apply


@dataclass(frozen=True)
class EncryptedField:
    model_name: str
    model: type[Any]
    table_name: str
    column_name: str
    raw_attr: str
    property_name: str

    @property
    def id(self) -> str:
        return f"{self.model_name}.{self.property_name}"


ENCRYPTED_FIELD_INVENTORY = (
    EncryptedField("User", User, "users", "totp_secret", "_totp_secret", "totp_secret"),
    EncryptedField("User", User, "users", "email", "_email", "email"),
    EncryptedField("User", User, "users", "smtp_server", "_smtp_server", "smtp_server"),
    EncryptedField("User", User, "users", "smtp_username", "_smtp_username", "smtp_username"),
    EncryptedField("User", User, "users", "smtp_password", "_smtp_password", "smtp_password"),
    EncryptedField("User", User, "users", "pgp_key", "_pgp_key", "pgp_key"),
    EncryptedField(
        "NotificationRecipient",
        NotificationRecipient,
        "notification_recipients",
        "email",
        "_email",
        "email",
    ),
    EncryptedField(
        "NotificationRecipient",
        NotificationRecipient,
        "notification_recipients",
        "pgp_key",
        "_pgp_key",
        "pgp_key",
    ),
    EncryptedField("FieldValue", FieldValue, "field_values", "_value", "_value", "value"),
)

USER_LEGACY_VALUES = {
    "totp_secret": "legacy-totp-secret",
    "email": "legacy@example.com",
    "smtp_server": "smtp.legacy.example",
    "smtp_username": "legacy-smtp-user",
    "smtp_password": "legacy-smtp-password",
    "pgp_key": "legacy public pgp key",
}

NOTIFICATION_RECIPIENT_LEGACY_VALUES = {
    "email": "recipient@example.com",
    "pgp_key": "recipient public pgp key",
}

USER_LONG_VALUES = {
    "totp_secret": "A" * User.TOTP_SECRET_MAX_LENGTH,
    "email": LONG_EMAIL,
    "smtp_server": f"smtp.{'s' * 250}",
    "smtp_username": "u" * User.SMTP_USERNAME_MAX_LENGTH,
    "smtp_password": "p" * User.SMTP_PASSWORD_MAX_LENGTH,
    "pgp_key": LONG_PGP_BLOCK,
}

NOTIFICATION_RECIPIENT_LONG_VALUES = {
    "email": LONG_EMAIL,
    "pgp_key": LONG_PGP_BLOCK,
}


def _legacy_fernet_token(plaintext: str) -> str:
    return (
        Fernet(LEGACY_FERNET_KEY.encode())
        .encrypt_at_time(plaintext.encode(), current_time=0)
        .decode()
    )


def _decrypt_fernet_token(ciphertext: str) -> str:
    return Fernet(LEGACY_FERNET_KEY.encode()).decrypt(ciphertext.encode()).decode()


def _property_calls_encrypted_field_decryptor(node: ast.FunctionDef) -> bool:
    encrypted_field_decryptors = {"decrypt_field", "_decrypt_encrypted_field"}
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name) and child.func.id in encrypted_field_decryptors:
            return True
        if isinstance(child.func, ast.Attribute) and child.func.attr in encrypted_field_decryptors:
            return True
    return False


def _decorator_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _model_properties_calling_decrypt_field() -> set[tuple[str, str]]:
    model_dir = Path(__file__).resolve().parents[1] / "hushline" / "model"
    encrypted_properties: set[tuple[str, str]] = set()

    for model_path in model_dir.glob("*.py"):
        tree = ast.parse(model_path.read_text())
        for class_node in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for method_node in (
                node for node in class_node.body if isinstance(node, ast.FunctionDef)
            ):
                is_property = any(
                    _decorator_name(decorator) == "property"
                    for decorator in method_node.decorator_list
                )
                if is_property and _property_calls_encrypted_field_decryptor(method_node):
                    encrypted_properties.add((class_node.name, method_node.name))

    return encrypted_properties


def _make_encrypted_field_value(user: User) -> FieldValue:
    field_definition = FieldDefinition(
        username=user.primary_username,
        label="Encrypted custom value",
        field_type=FieldType.TEXT,
        required=False,
        enabled=True,
        encrypted=True,
        choices=[],
    )
    message = Message(username_id=user.primary_username.id)
    db.session.add_all([field_definition, message])
    db.session.flush()
    return FieldValue(
        field_definition=field_definition,
        message=message,
        value=PGP_CIPHERTEXT,
        encrypted=True,
    )


def _object_for_field(field: EncryptedField, user: User) -> Any:
    if field.model is User:
        return user
    if field.model is NotificationRecipient:
        return NotificationRecipient(user=user)
    if field.model is FieldValue:
        return _make_encrypted_field_value(user)
    raise AssertionError(f"Unhandled encrypted field inventory entry: {field.id}")


def _plaintext_for_field(field: EncryptedField) -> str:
    if field.model is User:
        return USER_LEGACY_VALUES[field.property_name]
    if field.model is NotificationRecipient:
        return NOTIFICATION_RECIPIENT_LEGACY_VALUES[field.property_name]
    if field.model is FieldValue:
        return PGP_CIPHERTEXT
    raise AssertionError(f"Unhandled encrypted field inventory entry: {field.id}")


def _long_plaintext_for_field(field: EncryptedField) -> str:
    if field.model is User:
        return USER_LONG_VALUES[field.property_name]
    if field.model is NotificationRecipient:
        return NOTIFICATION_RECIPIENT_LONG_VALUES[field.property_name]
    if field.model is FieldValue:
        return LONG_PGP_CIPHERTEXT
    raise AssertionError(f"Unhandled encrypted field inventory entry: {field.id}")


def _stored_ciphertext(field: EncryptedField, row_id: int) -> str:
    column = getattr(field.model, field.raw_attr)
    ciphertext = db.session.scalar(
        select(column).where(field.model.id == row_id),
    )
    assert isinstance(ciphertext, str)
    return ciphertext


def _aead_aad_values(field: EncryptedField, obj: Any) -> dict[str, int]:
    if field.model is User:
        return {"user_id": obj.id}
    if field.model is NotificationRecipient:
        return {"notification_recipient_id": obj.id, "user_id": obj.user_id}
    if field.model is FieldValue:
        return {
            "field_definition_id": obj.field_definition_id,
            "field_value_id": obj.id,
            "message_id": obj.message_id,
        }
    raise AssertionError(f"Unhandled encrypted field inventory entry: {field.id}")


def _encrypted_field_id(field: EncryptedField) -> str:
    return field.id


def test_encrypted_field_property_inventory_is_complete() -> None:
    expected = {(field.model_name, field.property_name) for field in ENCRYPTED_FIELD_INVENTORY}
    assert _model_properties_calling_decrypt_field() == expected


def test_encrypted_field_inventory_columns_match_models() -> None:
    for field in ENCRYPTED_FIELD_INVENTORY:
        assert field.model.__tablename__ == field.table_name
        column = getattr(field.model, field.raw_attr).property.columns[0]
        assert column.name == field.column_name


def test_encrypted_field_domain_contract_covers_inventory() -> None:
    inventory_ids = {field.id for field in ENCRYPTED_FIELD_INVENTORY}
    assert set(ENCRYPTED_FIELD_CONTRACT_BY_ID) == inventory_ids

    domains = [contract.domain for contract in ENCRYPTED_FIELD_CONTRACTS]
    assert len(domains) == len(set(domains))

    for field in ENCRYPTED_FIELD_INVENTORY:
        contract = ENCRYPTED_FIELD_CONTRACT_BY_ID[field.id]
        assert contract.domain == f"hushline.encrypted-field.{field.table_name}.{field.column_name}"
        assert contract.table == field.table_name
        assert contract.column == field.column_name
        assert ENCRYPTED_FIELD_MUTABLE_AAD_NAMES.isdisjoint(contract.aad_fields)


def test_user_encrypted_properties_store_fernet_ciphertext(user: User) -> None:
    for field in ENCRYPTED_FIELD_INVENTORY:
        if field.model is not User:
            continue
        plaintext = USER_LEGACY_VALUES[field.property_name]
        setattr(user, field.property_name, plaintext)

        ciphertext = getattr(user, field.raw_attr)
        assert ciphertext != plaintext
        assert _decrypt_fernet_token(ciphertext) == plaintext


def test_notification_recipient_properties_store_fernet_ciphertext(user: User) -> None:
    recipient = NotificationRecipient(user=user)
    for field in ENCRYPTED_FIELD_INVENTORY:
        if field.model is not NotificationRecipient:
            continue
        plaintext = NOTIFICATION_RECIPIENT_LEGACY_VALUES[field.property_name]
        setattr(recipient, field.property_name, plaintext)

        ciphertext = getattr(recipient, field.raw_attr)
        assert ciphertext != plaintext
        assert _decrypt_fernet_token(ciphertext) == plaintext


def test_field_value_stores_encrypted_custom_message_value_as_fernet_ciphertext(
    user: User,
) -> None:
    field_value = _make_encrypted_field_value(user)

    assert field_value.encrypted is True
    assert field_value._value != PGP_CIPHERTEXT
    assert _decrypt_fernet_token(field_value._value) == PGP_CIPHERTEXT


def test_legacy_fernet_user_fields_decrypt_through_properties(user: User) -> None:
    for field in ENCRYPTED_FIELD_INVENTORY:
        if field.model is not User:
            continue
        plaintext = USER_LEGACY_VALUES[field.property_name]
        setattr(user, field.raw_attr, _legacy_fernet_token(plaintext))

        assert getattr(user, field.raw_attr) != plaintext
        assert getattr(user, field.property_name) == plaintext


def test_legacy_fernet_notification_recipient_fields_decrypt(user: User) -> None:
    recipient = NotificationRecipient(user=user)
    for field in ENCRYPTED_FIELD_INVENTORY:
        if field.model is not NotificationRecipient:
            continue
        plaintext = NOTIFICATION_RECIPIENT_LEGACY_VALUES[field.property_name]
        setattr(recipient, field.raw_attr, _legacy_fernet_token(plaintext))

        assert getattr(recipient, field.raw_attr) != plaintext
        assert getattr(recipient, field.property_name) == plaintext


def test_legacy_fernet_field_value_decrypts_encrypted_custom_message_value(
    user: User,
) -> None:
    field_value = _make_encrypted_field_value(user)
    field_value._value = _legacy_fernet_token(PGP_CIPHERTEXT)

    assert field_value.encrypted is True
    assert field_value._value != PGP_CIPHERTEXT
    assert field_value.value == PGP_CIPHERTEXT


@pytest.mark.parametrize(
    "field",
    ENCRYPTED_FIELD_INVENTORY,
    ids=_encrypted_field_id,
)
def test_versioned_envelope_field_ciphertext_decrypts_through_properties(
    user: User, field: EncryptedField
) -> None:
    plaintext = _plaintext_for_field(field)
    obj = _object_for_field(field, user)
    envelope = serialize_encrypted_field_envelope(_legacy_fernet_token(plaintext))
    setattr(obj, field.raw_attr, envelope)

    assert getattr(obj, field.raw_attr) != plaintext
    assert getattr(obj, field.property_name) == plaintext


@pytest.mark.parametrize(
    "field",
    ENCRYPTED_FIELD_INVENTORY,
    ids=_encrypted_field_id,
)
def test_configured_envelope_write_format_stores_one_envelope_through_properties(
    app: Any, user: User, field: EncryptedField
) -> None:
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
    plaintext = _plaintext_for_field(field)
    obj = _object_for_field(field, user)

    setattr(obj, field.property_name, plaintext)

    ciphertext = getattr(obj, field.raw_attr)
    assert ciphertext.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    parsed = parse_encrypted_field_envelope(ciphertext)
    assert parsed is not None
    assert not parsed.ciphertext.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert getattr(obj, field.property_name) == plaintext


@pytest.mark.parametrize(
    "field",
    ENCRYPTED_FIELD_INVENTORY,
    ids=_encrypted_field_id,
)
def test_envelope_write_round_trips_long_values_that_exceed_legacy_capacity(
    app: Any, user: User, field: EncryptedField
) -> None:
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
    plaintext = _long_plaintext_for_field(field)
    obj = _object_for_field(field, user)
    db.session.add(obj)

    setattr(obj, field.property_name, plaintext)
    db.session.flush()
    row_id = obj.id
    db.session.commit()

    ciphertext = _stored_ciphertext(field, row_id)
    assert ciphertext.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert len(ciphertext) > ENCRYPTED_FIELD_LEGACY_MAX_LENGTH

    db.session.expire_all()
    reloaded = db.session.get(field.model, row_id)
    assert reloaded is not None
    assert getattr(reloaded, field.property_name) == plaintext


@pytest.mark.parametrize(
    "field",
    ENCRYPTED_FIELD_INVENTORY,
    ids=_encrypted_field_id,
)
def test_configured_aes_gcm_write_format_stores_aad_bound_envelopes(
    app: Any, user: User, field: EncryptedField
) -> None:
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_AES_GCM
    plaintext = _plaintext_for_field(field)
    obj = _object_for_field(field, user)

    setattr(obj, field.property_name, plaintext)

    ciphertext = getattr(obj, field.raw_attr)
    assert ciphertext.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    parsed = parse_encrypted_field_aead_envelope(ciphertext)
    assert parsed.algorithm == "aes-256-gcm"
    assert ENCRYPTED_FIELD_CONTRACT_BY_ID[field.id].aad_fields == tuple(
        _aead_aad_values(field, obj)
    )
    assert getattr(obj, field.property_name) == plaintext


@pytest.mark.parametrize(
    "field",
    ENCRYPTED_FIELD_INVENTORY,
    ids=_encrypted_field_id,
)
def test_aes_gcm_ciphertext_copy_to_wrong_row_fails_closed(
    app: Any, user: User, user2: User, field: EncryptedField
) -> None:
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_AES_GCM
    plaintext = _plaintext_for_field(field)
    obj = _object_for_field(field, user)
    other = _object_for_field(field, user2)

    setattr(obj, field.property_name, plaintext)
    setattr(other, field.raw_attr, getattr(obj, field.raw_attr))

    with pytest.raises(InvalidToken):
        getattr(other, field.property_name)


def test_aes_gcm_ciphertext_copy_to_wrong_field_fails_closed(app: Any, user: User) -> None:
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_AES_GCM

    user.email = "wrong-field@example.com"
    user._pgp_key = user._email

    with pytest.raises(InvalidToken):
        user.pgp_key


@pytest.mark.parametrize(
    "field",
    ENCRYPTED_FIELD_INVENTORY,
    ids=_encrypted_field_id,
)
def test_malformed_encrypted_field_ciphertext_fails_closed(
    user: User, field: EncryptedField
) -> None:
    obj = _object_for_field(field, user)
    setattr(obj, field.raw_attr, "not-a-valid-fernet-token")

    with pytest.raises(InvalidToken):
        getattr(obj, field.property_name)
