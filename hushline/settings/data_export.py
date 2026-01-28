import csv
import io
import zipfile
from datetime import datetime
from typing import Iterable

from flask import Blueprint, Response, abort, flash, redirect, send_file, session, url_for
from sqlalchemy.orm import selectinload

from hushline.auth import authentication_required
from hushline.crypto import encrypt_bytes
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    FieldDefinition,
    FieldValue,
    Message,
    MessageStatusText,
    User,
    Username,
)
from hushline.settings.forms import DataExportForm


def _write_csv(
    table_name: str, columns: Iterable[str], rows: list[dict[str, object]]
) -> tuple[str, str]:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(columns))
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return f"db/{table_name}.csv", output.getvalue()


def _slugify(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip().lower())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "field"


def register_data_export_routes(bp: Blueprint) -> None:
    @bp.route("/data-export", methods=["POST"])
    @authentication_required
    def data_export() -> Response:
        form = DataExportForm()
        if not form.validate_on_submit():
            abort(400)
        user_id = session["user_id"]
        user = db.session.get(User, user_id)

        usernames_rows: list[dict[str, object]] = [
            dict(row)
            for row in db.session.execute(
                db.select(Username.__table__).where(  # type: ignore[attr-defined]
                    Username.__table__.c.user_id == user_id  # type: ignore[attr-defined]
                )
            )
            .mappings()
            .all()
        ]
        username_ids = [row["id"] for row in usernames_rows]

        messages_rows: list[dict[str, object]] = []
        if username_ids:
            messages_rows = [
                dict(row)
                for row in db.session.execute(
                    db.select(Message.__table__).where(  # type: ignore[attr-defined]
                        Message.__table__.c.username_id.in_(  # type: ignore[attr-defined]
                            username_ids
                        )
                    )
                )
                .mappings()
                .all()
            ]
        message_ids = [row["id"] for row in messages_rows]

        field_def_rows: list[dict[str, object]] = []
        if username_ids:
            field_def_rows = [
                dict(row)
                for row in db.session.execute(
                    db.select(FieldDefinition.__table__).where(  # type: ignore[attr-defined]
                        FieldDefinition.__table__.c.username_id.in_(  # type: ignore[attr-defined]
                            username_ids
                        )
                    )
                )
                .mappings()
                .all()
            ]
        field_values_rows: list[dict[str, object]] = []
        if message_ids:
            field_values_rows = [
                dict(row)
                for row in db.session.execute(
                    db.select(FieldValue.__table__).where(  # type: ignore[attr-defined]
                        FieldValue.__table__.c.message_id.in_(  # type: ignore[attr-defined]
                            message_ids
                        )
                    )
                )
                .mappings()
                .all()
            ]

        status_text_rows: list[dict[str, object]] = [
            dict(row)
            for row in db.session.execute(
                db.select(MessageStatusText.__table__).where(  # type: ignore[attr-defined]
                    MessageStatusText.__table__.c.user_id == user_id  # type: ignore[attr-defined]
                )
            )
            .mappings()
            .all()
        ]

        auth_log_rows: list[dict[str, object]] = [
            dict(row)
            for row in db.session.execute(
                db.select(AuthenticationLog.__table__).where(  # type: ignore[attr-defined]
                    AuthenticationLog.__table__.c.user_id == user_id  # type: ignore[attr-defined]
                )
            )
            .mappings()
            .all()
        ]

        user_rows: list[dict[str, object]] = [
            dict(row)
            for row in db.session.execute(
                db.select(User.__table__).where(  # type: ignore[attr-defined]
                    User.__table__.c.id == user_id  # type: ignore[attr-defined]
                )
            )
            .mappings()
            .all()
        ]

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            csv_files = [
                _write_csv(
                    "users",
                    User.__table__.columns.keys(),  # type: ignore[attr-defined]
                    user_rows,
                ),
                _write_csv(
                    "usernames",
                    Username.__table__.columns.keys(),  # type: ignore[attr-defined]
                    usernames_rows,
                ),
                _write_csv(
                    "messages",
                    Message.__table__.columns.keys(),  # type: ignore[attr-defined]
                    messages_rows,
                ),
                _write_csv(
                    "field_definitions",
                    FieldDefinition.__table__.columns.keys(),  # type: ignore[attr-defined]
                    field_def_rows,
                ),
                _write_csv(
                    "field_values",
                    FieldValue.__table__.columns.keys(),  # type: ignore[attr-defined]
                    field_values_rows,
                ),
                _write_csv(
                    "message_status_text",
                    MessageStatusText.__table__.columns.keys(),  # type: ignore[attr-defined]
                    status_text_rows,
                ),
                _write_csv(
                    "authentication_logs",
                    AuthenticationLog.__table__.columns.keys(),  # type: ignore[attr-defined]
                    auth_log_rows,
                ),
            ]
            for filename, content in csv_files:
                zip_file.writestr(filename, content)

            if username_ids:
                messages = db.session.scalars(
                    db.select(Message)
                    .where(Message.username_id.in_(username_ids))
                    .options(
                        selectinload(Message.field_values).selectinload(FieldValue.field_definition)
                    )
                ).all()
                for message in messages:
                    for field_value in message.field_values:
                        if not field_value.encrypted:
                            continue
                        value = field_value.value
                        if not value or not value.startswith("-----BEGIN PGP MESSAGE-----"):
                            continue
                        label = (
                            field_value.field_definition.label
                            if field_value.field_definition
                            else "field"
                        )
                        label_slug = _slugify(label)
                        filename = (
                            f"pgp_messages/{message.public_id}-{label_slug}-{field_value.id}.asc"
                        )
                        zip_file.writestr(filename, value)

        zip_buffer.seek(0)
        export_bytes = zip_buffer.getvalue()
        encrypt_export = form.encrypt_export.data
        if encrypt_export:
            if not user or not user.pgp_key:
                flash("⛔️ Add a PGP key to encrypt your export.")
                return redirect(url_for("settings.encryption"))
            encrypted = encrypt_bytes(export_bytes, user.pgp_key)
            if not encrypted:
                flash("⛔️ Failed to encrypt export. Please try again.")
                return redirect(url_for("settings.advanced"))
            export_bytes = encrypted

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        username_slug = user.primary_username.username if user else "user"
        suffix = "zip.asc" if encrypt_export else "zip"
        download_name = f"hushline-data-{username_slug}-{timestamp}.{suffix}"
        return send_file(
            io.BytesIO(export_bytes),
            mimetype="application/pgp-encrypted" if encrypt_export else "application/zip",
            as_attachment=True,
            download_name=download_name,
        )
