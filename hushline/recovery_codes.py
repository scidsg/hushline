import base64
import re
import secrets
from datetime import UTC, datetime
from hashlib import sha256

from hushline.db import db
from hushline.model import RecoveryCode, RecoveryCodeBatch, User

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_ENTROPY_BYTES = 20
RECOVERY_CODE_NORMALIZED_LENGTH = 32


def normalize_recovery_code(value: str) -> str:
    return "".join(character for character in value.upper() if character not in "- \t\r\n")


def hash_recovery_code(user_id: int, value: str) -> bytes:
    normalized = normalize_recovery_code(value)
    if re.fullmatch(r"[A-Z2-7]{32}", normalized) is None:
        raise ValueError("Invalid recovery code format")
    return sha256(f"{user_id}:{normalized}".encode("ascii")).digest()


def _generate_code() -> str:
    encoded = base64.b32encode(secrets.token_bytes(RECOVERY_CODE_ENTROPY_BYTES)).decode("ascii")
    return "-".join(encoded[index : index + 4] for index in range(0, len(encoded), 4))


def has_usable_recovery_codes(user_id: int) -> bool:
    return (
        db.session.scalar(
            db.select(RecoveryCode.id)
            .join(RecoveryCodeBatch)
            .where(
                RecoveryCodeBatch.user_id == user_id,
                RecoveryCodeBatch.acknowledged_at.is_not(None),
                RecoveryCodeBatch.invalidated_at.is_(None),
                RecoveryCode.consumed_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def generate_recovery_codes(user: User) -> tuple[RecoveryCodeBatch, list[str]]:
    now = datetime.now(UTC)
    db.session.scalar(db.select(User.id).where(User.id == user.id).with_for_update())
    db.session.execute(
        db.update(RecoveryCodeBatch)
        .where(
            RecoveryCodeBatch.user_id == user.id,
            RecoveryCodeBatch.invalidated_at.is_(None),
        )
        .values(invalidated_at=now)
    )
    batch = RecoveryCodeBatch(user_id=user.id, created_at=now)
    db.session.add(batch)
    db.session.flush()

    plaintext_codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        code = _generate_code()
        plaintext_codes.append(code)
        db.session.add(RecoveryCode(batch_id=batch.id, code_hash=hash_recovery_code(user.id, code)))
    db.session.commit()
    return batch, plaintext_codes


def acknowledge_recovery_codes(*, user_id: int, batch_id: int) -> bool:
    now = datetime.now(UTC)
    acknowledged_id = db.session.scalar(
        db.update(RecoveryCodeBatch)
        .where(
            RecoveryCodeBatch.id == batch_id,
            RecoveryCodeBatch.user_id == user_id,
            RecoveryCodeBatch.acknowledged_at.is_(None),
            RecoveryCodeBatch.invalidated_at.is_(None),
        )
        .values(acknowledged_at=now)
        .returning(RecoveryCodeBatch.id)
    )
    return acknowledged_id is not None


def consume_recovery_code(*, user_id: int, value: str) -> bool:
    normalized = normalize_recovery_code(value)
    if (
        len(normalized) != RECOVERY_CODE_NORMALIZED_LENGTH
        or re.fullmatch(r"[A-Z2-7]{32}", normalized) is None
    ):
        return False

    db.session.scalar(db.select(User.id).where(User.id == user_id).with_for_update())

    batch_ids = db.select(RecoveryCodeBatch.id).where(
        RecoveryCodeBatch.user_id == user_id,
        RecoveryCodeBatch.acknowledged_at.is_not(None),
        RecoveryCodeBatch.invalidated_at.is_(None),
    )
    consumed_id = db.session.scalar(
        db.update(RecoveryCode)
        .where(
            RecoveryCode.batch_id.in_(batch_ids),
            RecoveryCode.code_hash == hash_recovery_code(user_id, normalized),
            RecoveryCode.consumed_at.is_(None),
        )
        .values(consumed_at=datetime.now(UTC))
        .returning(RecoveryCode.id)
    )
    return consumed_id is not None
