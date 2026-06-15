from uuid import uuid4

from sqlalchemy import text

from hushline.db import db

CONVERSATION_IDS = [9801, 9802, 9803]


def _conversation_public_id_column_count() -> int:
    return db.session.scalar(
        text(
            """
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'conversations'
              AND column_name = 'public_id'
            """
        )
    )


def _insert_conversations(*, include_public_id: bool) -> None:
    for conversation_id in CONVERSATION_IDS:
        if include_public_id:
            db.session.execute(
                text(
                    """
                    INSERT INTO conversations (id, public_id)
                    VALUES (:id, :public_id)
                    """
                ),
                {"id": conversation_id, "public_id": str(uuid4())},
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO conversations (id)
                    VALUES (:id)
                    """
                ),
                {"id": conversation_id},
            )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_conversations(include_public_id=False)

    def check_upgrade(self) -> None:
        assert _conversation_public_id_column_count() == 1
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM conversations
                    WHERE public_id IS NULL
                    """
                )
            )
            == 0
        )
        assert db.session.scalar(
            text(
                """
                    SELECT count(DISTINCT public_id)
                    FROM conversations
                    """
            )
        ) == len(CONVERSATION_IDS)


class DowngradeTester:
    def load_data(self) -> None:
        _insert_conversations(include_public_id=True)

    def check_downgrade(self) -> None:
        assert _conversation_public_id_column_count() == 0
        assert db.session.scalar(
            text(
                """
                    SELECT count(*)
                    FROM conversations
                    WHERE id = ANY(:conversation_ids)
                    """
            ),
            {"conversation_ids": CONVERSATION_IDS},
        ) == len(CONVERSATION_IDS)
