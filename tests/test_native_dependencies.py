from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from greenlet import getcurrent, greenlet
from pysequoia import Cert, encrypt


def test_cryptography_fernet_and_scrypt_runtime() -> None:
    key = Fernet.generate_key()
    fernet = Fernet(key)

    token = fernet.encrypt_at_time(b"native-runtime-check", current_time=0)
    assert fernet.decrypt(token) == b"native-runtime-check"

    kdf = Scrypt(salt=b"\x00" * 16, length=32, n=2, r=1, p=1)
    derived_key = kdf.derive(b"native-runtime-check")

    assert len(derived_key) == 32


def test_pysequoia_cert_parse_and_encrypt_runtime() -> None:
    public_key = (Path(__file__).parent / "test_pgp_key.txt").read_text(encoding="utf-8").strip()

    certificate = Cert.from_bytes(public_key.encode())
    encrypted_message = encrypt([certificate], b"native-runtime-check")

    if isinstance(encrypted_message, str):
        encrypted_message = encrypted_message.encode("utf-8")

    assert b"BEGIN PGP MESSAGE" in encrypted_message


def test_psycopg_connects_and_executes_query(database: str) -> None:
    conninfo = f"postgresql://hushline:hushline@postgres:5432/{database}"

    with psycopg.connect(conninfo) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()

    assert result == (1,)


def test_greenlet_switch_runtime() -> None:
    parent = getcurrent()
    history: list[str] = []

    def child() -> str:
        history.append("child-start")
        resume_value = parent.switch("child-yield")
        history.append(resume_value)
        return "child-done"

    task = greenlet(child)

    assert task.switch() == "child-yield"
    assert not task.dead
    assert task.switch("parent-resume") == "child-done"
    assert task.dead
    assert history == ["child-start", "parent-resume"]
