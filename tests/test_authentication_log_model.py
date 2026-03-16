from hushline.model import AuthenticationLog


def test_authentication_log_init_sets_optional_fields() -> None:
    log = AuthenticationLog(
        user_id=42,
        successful=False,
        otp_code="123456",
        timecode=12345678,
    )

    assert log.user_id == 42
    assert log.successful is False
    assert log.otp_code == "123456"
    assert log.timecode == 12345678
