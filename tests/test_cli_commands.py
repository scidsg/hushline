from unittest.mock import MagicMock, patch

from flask import Flask

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting


def test_reg_settings_command_outputs_current_values(app: Flask) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["reg", "settings"])

    assert result.exit_code == 0
    assert "Registration Enabled: False" in result.output
    assert "Registration Codes Required: False" in result.output


def test_reg_toggle_commands_update_org_settings(app: Flask) -> None:
    runner = app.test_cli_runner()

    result_enabled = runner.invoke(args=["reg", "registration-enabled", "true"])
    result_codes = runner.invoke(args=["reg", "registration-codes-required", "true"])

    assert result_enabled.exit_code == 0
    assert result_codes.exit_code == 0
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED) is True
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_CODES_REQUIRED) is True


def test_reg_code_commands_create_list_and_delete(app: Flask) -> None:
    runner = app.test_cli_runner()

    empty_result = runner.invoke(args=["reg", "code-list"])
    assert empty_result.exit_code == 0
    assert "No invite codes found." in empty_result.output

    create_result = runner.invoke(args=["reg", "code-create"])
    assert create_result.exit_code == 0
    assert "Invite code " in create_result.output
    assert " created." in create_result.output

    invite_code = db.session.scalar(db.select(InviteCode))
    assert invite_code is not None

    listed_result = runner.invoke(args=["reg", "code-list"])
    assert listed_result.exit_code == 0
    assert invite_code.code in listed_result.output

    delete_result = runner.invoke(args=["reg", "code-delete", invite_code.code])
    assert delete_result.exit_code == 0
    assert f"Invite code {invite_code.code} deleted." in delete_result.output
    assert db.session.scalar(db.select(InviteCode).filter_by(code=invite_code.code)) is None

    missing_result = runner.invoke(args=["reg", "code-delete", "does-not-exist"])
    assert missing_result.exit_code == 0
    assert "Invite code not found." in missing_result.output


def test_reg_code_create_avoids_dash_prefixed_codes(app: Flask) -> None:
    runner = app.test_cli_runner()

    with patch(
        "hushline.model.invite_code.secrets.token_urlsafe",
        side_effect=["-dashprefixed", "safe-code-token"],
    ):
        create_result = runner.invoke(args=["reg", "code-create"])

    assert create_result.exit_code == 0
    invite_code = db.session.scalar(db.select(InviteCode))
    assert invite_code is not None
    assert invite_code.code == "safe-code-token"
    assert not invite_code.code.startswith("-")

    delete_result = runner.invoke(args=["reg", "code-delete", invite_code.code])
    assert delete_result.exit_code == 0
    assert f"Invite code {invite_code.code} deleted." in delete_result.output


def test_stripe_configure_skips_when_secret_missing(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    runner = app.test_cli_runner()

    with (
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_products,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    init_stripe.assert_not_called()
    create_products.assert_not_called()


def test_stripe_configure_runs_premium_setup_when_secret_present(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    runner = app.test_cli_runner()

    with (
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_products,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    init_stripe.assert_called_once()
    create_products.assert_called_once()


def test_stripe_start_worker_skips_without_secret(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    runner = app.test_cli_runner()

    with patch.object(app.logger, "error") as logger_error:
        result = runner.invoke(args=["stripe", "start-worker"])

    assert result.exit_code == 0
    logger_error.assert_called_once()


def test_stripe_start_worker_runs_async_worker(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    runner = app.test_cli_runner()
    worker_coro = object()

    with (
        patch(
            "hushline.cli_stripe.premium.worker", new=MagicMock(return_value=worker_coro)
        ) as worker_mock,
        patch("hushline.cli_stripe.asyncio.run") as asyncio_run,
    ):
        result = runner.invoke(args=["stripe", "start-worker"])

    assert result.exit_code == 0
    worker_mock.assert_called_once_with(app)
    asyncio_run.assert_called_once_with(worker_coro)
