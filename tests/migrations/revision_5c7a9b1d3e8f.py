from sqlalchemy import text

from hushline.db import db


def _insert_chat_key() -> None:
    db.session.execute(
        text(
            """
            INSERT INTO users (
                id,
                is_admin,
                is_suspended,
                password_hash,
                session_id
            )
            VALUES (9701, false, false, '$scrypt$', 'session-9701')
            """
        )
    )
    db.session.execute(
        text(
            """
            INSERT INTO chat_keys (
                id,
                user_id,
                key_version,
                public_key,
                encrypted_private_key,
                kdf_algorithm,
                kdf_params,
                kdf_salt,
                wrapping_algorithm
            )
            VALUES (
                9701,
                9701,
                1,
                '{"kty":"EC","crv":"P-256","x":"x","y":"y"}',
                '{"algorithm":"AES-GCM","iv":"iv","ciphertext":"ciphertext"}',
                'PBKDF2-SHA-256',
                '{"iterations": 310000}'::json,
                'salt',
                'AES-GCM'
            )
            """
        )
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_chat_key()

    def check_upgrade(self) -> None:
        row = db.session.execute(
            text(
                """
                SELECT data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'chat_keys'
                  AND column_name = 'public_signing_key'
                """
            )
        ).one()
        assert row == ("text", "YES")

        assert (
            db.session.scalar(text("SELECT public_signing_key FROM chat_keys WHERE id = 9701"))
            is None
        )


class DowngradeTester:
    def load_data(self) -> None:
        db.session.execute(
            text(
                """
                INSERT INTO users (
                    id,
                    is_admin,
                    is_suspended,
                    password_hash,
                    session_id
                )
                VALUES (9702, false, false, '$scrypt$', 'session-9702')
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO chat_keys (
                    id,
                    user_id,
                    key_version,
                    public_key,
                    public_signing_key,
                    encrypted_private_key,
                    kdf_algorithm,
                    kdf_params,
                    kdf_salt,
                    wrapping_algorithm
                )
                VALUES (
                    9702,
                    9702,
                    1,
                    '{"kty":"EC","crv":"P-256","x":"x","y":"y"}',
                    '{"kty":"EC","crv":"P-256","x":"sx","y":"sy"}',
                    '{"algorithm":"AES-GCM","iv":"iv","ciphertext":"ciphertext"}',
                    'PBKDF2-SHA-256',
                    '{"iterations": 310000}'::json,
                    'salt',
                    'AES-GCM'
                )
                """
            )
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'chat_keys'
                      AND column_name = 'public_signing_key'
                    """
                )
            )
            == 0
        )
