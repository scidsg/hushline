from unittest.mock import patch

from hushline.model import InviteCode


def test_invite_code_repr_includes_code() -> None:
    with patch("hushline.model.invite_code.secrets.token_urlsafe", return_value="invite-123"):
        invite_code = InviteCode()

    assert repr(invite_code) == "<InviteCode invite-123>"
