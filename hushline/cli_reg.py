import click
from flask import Flask
from flask.cli import AppGroup

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting


def register_reg_commands(app: Flask) -> None:
    reg_cli = AppGroup("reg", help="Registration settings commands")

    @reg_cli.command("settings")
    def settings() -> None:
        """View registration settings"""
        registration_enabled = OrganizationSetting.fetch_one(
            OrganizationSetting.REGISTRATION_ENABLED
        )
        registration_codes_required = OrganizationSetting.fetch_one(
            OrganizationSetting.REGISTRATION_CODES_REQUIRED
        )
        click.echo(f"Registration Enabled: {registration_enabled}")
        click.echo(f"Registration Codes Required: {registration_codes_required}")

    @reg_cli.command("registration-enabled")
    @click.argument("value", type=bool)
    def registration_enabled(value: bool) -> None:
        """Set REGISTRATION_ENABLED to the given value"""
        OrganizationSetting.upsert(
            key=OrganizationSetting.REGISTRATION_ENABLED,
            value=value,
        )
        db.session.commit()

    @reg_cli.command("registration-codes-required")
    @click.argument("value", type=bool)
    def registration_quotes_required(value: bool) -> None:
        """Set REGISTRATION_CODES_REQUIRED to the given value"""
        OrganizationSetting.upsert(
            key=OrganizationSetting.REGISTRATION_CODES_REQUIRED,
            value=value,
        )
        db.session.commit()

    @reg_cli.command("code-list")
    def code_list() -> None:
        """List all invite codes"""
        codes = db.session.scalars(db.select(InviteCode)).all()
        if len(codes) == 0:
            click.echo("No invite codes found.")
        for code in codes:
            click.echo(f"{code.code} (expires {code.expiration_date})")

    @reg_cli.command("code-create")
    def code_create() -> None:
        """Create an invite code"""
        new_invite_code = InviteCode()
        db.session.add(new_invite_code)
        db.session.commit()
        click.echo(f"Invite code {new_invite_code.code} created.")

    @reg_cli.command("code-delete")
    @click.argument("code")
    def code_delete(code: str) -> None:
        """Delete an invite code"""
        invite_code = db.session.scalars(db.select(InviteCode).filter_by(code=code)).one_or_none()
        if invite_code is None:
            click.echo("Invite code not found.")
            return
        db.session.delete(invite_code)
        db.session.commit()
        click.echo(f"Invite code {invite_code.code} deleted.")

    app.cli.add_command(reg_cli)
