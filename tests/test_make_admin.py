import pytest
from flask import Flask

from hushline.db import db
from hushline.make_admin import main, toggle_admin
from hushline.model import User, Username


def test_toggle_admin_prints_when_user_missing(
    app: Flask, capsys: pytest.CaptureFixture[str]
) -> None:
    toggle_admin("missing-user")
    captured = capsys.readouterr()
    assert captured.out.strip() == "User not found."


def test_toggle_admin_flips_admin_flag_case_insensitive(
    app: Flask, capsys: pytest.CaptureFixture[str], user_password: str
) -> None:
    user = User(password=user_password)
    db.session.add(user)
    db.session.flush()
    uname = Username(user_id=user.id, _username="CaseUser", is_primary=True)
    db.session.add(uname)
    db.session.commit()
    assert user.is_admin is False

    toggle_admin("caseuser")
    db.session.refresh(user)
    assert user.is_admin is True

    toggle_admin("CASEUSER")
    db.session.refresh(user)
    assert user.is_admin is False

    captured = capsys.readouterr()
    assert "admin status toggled to True." in captured.out
    assert "admin status toggled to False." in captured.out


def test_make_admin_main_without_username_exits(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["make_admin.py"])

    assert rc == 1
    captured = capsys.readouterr()
    assert "Usage: python make_admin.py <username>" in captured.out


def test_make_admin_main_with_username_runs(app: Flask, user: User) -> None:
    rc = main(["make_admin.py", user.primary_username.username])
    assert rc == 0
