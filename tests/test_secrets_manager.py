from hushline.crypto import SecretsManager


def test_device_salt_is_static_once_created() -> None:
    vault = SecretsManager()

    salt = vault._summon_device_salt()
    assert isinstance(salt, bytes)
    assert len(salt) == vault._secret_salt_length
    assert salt == vault._summon_device_salt()
