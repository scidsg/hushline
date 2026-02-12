import csv
import io
import zipfile
from datetime import UTC, datetime
from typing import Iterable

from flask import Blueprint, abort, flash, redirect, send_file, session, url_for
from flask.typing import ResponseReturnValue
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
    cleaned = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in value.strip().lower())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "field"


def _fetch_rows(user_id: int) -> dict[str, list[dict[str, object]]]:
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

    return {
        "usernames": usernames_rows,
        "messages": messages_rows,
        "field_definitions": field_def_rows,
        "field_values": field_values_rows,
        "message_status_text": status_text_rows,
        "authentication_logs": auth_log_rows,
        "users": user_rows,
    }


def _write_csv_bundle(rows: dict[str, list[dict[str, object]]]) -> list[tuple[str, str]]:
    return [
        _write_csv(
            "users",
            User.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["users"],
        ),
        _write_csv(
            "usernames",
            Username.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["usernames"],
        ),
        _write_csv(
            "messages",
            Message.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["messages"],
        ),
        _write_csv(
            "field_definitions",
            FieldDefinition.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["field_definitions"],
        ),
        _write_csv(
            "field_values",
            FieldValue.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["field_values"],
        ),
        _write_csv(
            "message_status_text",
            MessageStatusText.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["message_status_text"],
        ),
        _write_csv(
            "authentication_logs",
            AuthenticationLog.__table__.columns.keys(),  # type: ignore[attr-defined]
            rows["authentication_logs"],
        ),
    ]


def _write_pgp_messages(zip_file: zipfile.ZipFile, username_ids: list[int]) -> None:
    if not username_ids:
        return
    messages = db.session.scalars(
        db.select(Message)
        .where(Message.username_id.in_(username_ids))
        .options(selectinload(Message.field_values).selectinload(FieldValue.field_definition))
    ).all()
    for message in messages:
        for field_value in message.field_values:
            if not field_value.encrypted:
                continue
            value = field_value.value
            if not value or not value.startswith("-----BEGIN PGP MESSAGE-----"):
                continue
            label = field_value.field_definition.label if field_value.field_definition else "field"
            label_slug = _slugify(label)
            public_id = message.public_id or f"message-{message.id}"
            filename = f"pgp_messages/{public_id}-{label_slug}-{field_value.id}.asc"
            zip_file.writestr(filename, value)


def _build_zip(user_id: int) -> bytes:
    rows = _fetch_rows(user_id)
    username_ids: list[int] = []
    for row in rows["usernames"]:
        value = row.get("id")
        if isinstance(value, int):
            username_ids.append(value)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        csv_files = _write_csv_bundle(rows)
        for filename, content in csv_files:
            zip_file.writestr(filename, content)
        _write_pgp_messages(zip_file, username_ids)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def register_data_export_routes(bp: Blueprint) -> None:
    @bp.route("/data-export", methods=["POST"])
    @authentication_required
    def data_export() -> ResponseReturnValue:
        form = DataExportForm()
        if not form.validate_on_submit():
            abort(400)
        user_id = session["user_id"]
        user = db.session.get(User, user_id)

        export_bytes = _build_zip(user_id)
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

        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        username_slug = user.primary_username.username if user else "user"
        suffix = "zip.asc" if encrypt_export else "zip"
        download_name = f"hushline-data-{username_slug}-{timestamp}.{suffix}"
        return send_file(
            io.BytesIO(export_bytes),
            mimetype="application/pgp-encrypted" if encrypt_export else "application/zip",
            as_attachment=True,
            download_name=download_name,
        )
