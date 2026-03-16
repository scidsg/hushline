from unittest.mock import MagicMock, patch

from flask import Flask
from werkzeug.security import generate_password_hash

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, Tier, User


def test_reg_settings_command_outputs_current_values(app: Flask) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["reg", "settings"])

    assert result.exit_code == 0
    assert "Registration Enabled: False" in result.output
    assert "Registration Codes Required: True" in result.output


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


def test_password_hash_report_outputs_legacy_count_and_removal_gate(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    user._password_hash = generate_password_hash(user_password, method="scrypt")
    db.session.commit()

    assert user2.password_hash.startswith("$scrypt$")

    result = runner.invoke(args=["password-hash", "report"])

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 1" in result.output
    assert (
        "Legacy verification success counter: "
        "password_hash_verification_success_total hash_format=passlib_scrypt"
    ) in result.output
    assert (
        "Rehash-on-auth counters: password_hash_rehash_on_auth_success_total, "
        "password_hash_rehash_on_auth_failure_total"
    ) in result.output
    assert "legacy rows must stay at 0 for one full release cycle" in result.output
    assert (
        "Current build verification support: passlib $scrypt$ and native prefix-based hashes."
        in result.output
    )
    assert (
        "Measured legacy verification successes: provide --legacy-verification-successes <count>"
        in result.output
    )
    assert "Passlib removal readiness: blocked" in result.output


def test_password_hash_report_blocks_when_measured_legacy_successes_non_zero(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    native_hash = generate_password_hash(user_password, method="scrypt")
    user._password_hash = native_hash
    user2._password_hash = native_hash
    db.session.commit()

    result = runner.invoke(
        args=[
            "password-hash",
            "report",
            "--legacy-verification-successes",
            "3",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 0" in result.output
    assert "Measured legacy verification successes: 3" in result.output
    assert "Legacy verifier path: passlib_dependency" in result.output
    assert "Passlib removal readiness: blocked" in result.output
    assert "Passlib removal reason: measured legacy verification success volume is non-zero" in (
        result.output
    )


def test_password_hash_can_remove_passlib_blocks_when_legacy_rows_remain(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    user._password_hash = generate_password_hash(user_password, method="scrypt")
    db.session.commit()

    assert user2.password_hash.startswith("$scrypt$")

    result = runner.invoke(
        args=[
            "password-hash",
            "can-remove-passlib",
            "--legacy-verification-successes",
            "0",
        ]
    )

    assert result.exit_code == 1
    assert "Legacy passlib scrypt rows: 1" in result.output
    assert "Measured legacy verification successes: 0" in result.output
    assert "Error: Passlib removal readiness: blocked (legacy passlib scrypt rows remain)" in (
        result.output
    )


def test_password_hash_can_remove_passlib_succeeds_when_legacy_rows_and_volume_are_zero(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    native_hash = generate_password_hash(user_password, method="scrypt")
    user._password_hash = native_hash
    user2._password_hash = native_hash
    db.session.commit()

    result = runner.invoke(
        args=[
            "password-hash",
            "can-remove-passlib",
            "--legacy-verification-successes",
            "0",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 0" in result.output
    assert "Measured legacy verification successes: 0" in result.output
    assert "Legacy verifier path: passlib_dependency" in result.output
    assert "Passlib removal readiness: ready" in result.output


def test_password_hash_can_remove_passlib_accepts_reviewed_in_repo_legacy_verifier_path(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    user._password_hash = generate_password_hash(user_password, method="scrypt")
    db.session.commit()

    assert user2.password_hash.startswith("$scrypt$")

    result = runner.invoke(
        args=[
            "password-hash",
            "can-remove-passlib",
            "--legacy-verification-successes",
            "7",
            "--reviewed-in-repo-legacy-verifier",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 1" in result.output
    assert "Measured legacy verification successes: 7" in result.output
    assert "Legacy verifier path: reviewed_in_repo_legacy_verifier" in result.output
    assert "Passlib removal readiness: ready" in result.output


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


def test_stripe_configure_creates_missing_tiers_when_lookup_returns_none(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    runner = app.test_cli_runner()
    db.session.execute(db.delete(Tier))
    db.session.commit()

    with (
        patch("hushline.cli_stripe.Tier.free_tier", return_value=None),
        patch("hushline.cli_stripe.Tier.business_tier", return_value=None),
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_products,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    assert db.session.scalar(db.select(Tier).filter_by(name="Free")) is not None
    assert db.session.scalar(db.select(Tier).filter_by(name="Business")) is not None
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
