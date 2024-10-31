import mimetypes
import os
import shutil
from io import IOBase
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig
from flask import Blueprint, Flask, abort, current_app, redirect, send_from_directory, session
from werkzeug.routing import BuildError
from werkzeug.wrappers.response import Response

from .db import db
from .model import FileUpload, Message, Username


def init_app(app: Flask) -> None:
    # TODO awful hack for prototyping, move to real config
    for k, v in os.environ.items():
        if k.startswith("BLOB_STORAGE"):
            app.config[k] = v

    app.register_blueprint(create_blueprint(), url_prefix="/assets")


def create_blueprint() -> Blueprint:
    bp = Blueprint("storage", __name__)

    @bp.route("/messsages/<int:message_id>/encrypted-file/<uuid:file_id>.gpg")
    def encrypted_file(message_id: int, file_id: UUID) -> Response:
        file = db.session.scalar(
            db.select(FileUpload)
            .join(Message)
            .join(Username)
            .filter(
                Message.id == message_id,
                Username.user_id == session["user_id"],
                FileUpload.id == file_id,
            )
        ).one_or_none()
        if file is None:
            abort(404)

        return private_store.serve_encrypted_file(file)

    return bp


class StorageBase:
    __NAME_BASE = "BLOB_STORAGE"

    def __init__(self, config_prefix: Optional[str] = None) -> None:
        self._config_prefix = config_prefix

    def _env_var(self, name: str) -> str:
        env_var = self.__NAME_BASE
        if self._config_prefix:
            env_var += "_" + self._config_prefix
        return f"{env_var}_{name}"

    def _ext_name(self) -> str:
        if self._config_prefix:
            return f"{self.__NAME_BASE}_{self._config_prefix}"
        return self.__NAME_BASE


class StorageDriver(StorageBase):
    def _put(self, path: str, readable: IOBase) -> None:
        raise NotImplementedError

    def _serve(self, path: str) -> Response:
        raise NotImplementedError


class FsDriver(StorageDriver):
    """
    Config options:
    - BLOB_STORAGE_FS_ROOT
    """

    def __init__(self, app: Flask, config_prefix: Optional[str] = None) -> None:
        super().__init__(config_prefix)

        root = Path(app.config[self._env_var("FS_ROOT")])
        if root.absolute() != root:  # needed for security checks later
            raise ValueError(f"Path {root!r} was not absolute")
        self.__root = root

    def __full_path(self, path: str) -> Path:
        full_path = self.__root / path
        if full_path.absolute() != full_path:
            raise ValueError(f"Path {full_path!r} was not absolute")
        return full_path

    def _put(self, path: str, readable: IOBase) -> None:
        full_path = self.__full_path(path)
        # TODO make and check permissions
        os.makedirs(full_path.parent, exist_ok=True)
        with open(full_path, "wb") as f:
            shutil.copyfileobj(readable, f)

    def _serve(self, path: str) -> Response:
        return send_from_directory(self.__root, path)


class S3Driver(StorageDriver):
    """Config options
    - BLOB_STORAGE_S3_REGION
    - BLOB_STORAGE_S3_ENDPOINT
    - BLOB_STORAGE_S3_ACCESS_KEY
    - BLOB_STORAGE_S3_SECRET_KEY
    - BLOB_STORAGE_S3_BUCKET
    - BLOB_STORAGE_S3_ACL
    - BLOB_STORAGE_S3_CDN_ENDPOINT
    """

    def __init__(self, app: Flask, config_prefix: Optional[str] = None) -> None:
        super().__init__(config_prefix)

        self.__bucket = app.config[self._env_var("S3_BUCKET")]
        self.__cdn_endpoint = app.config[self._env_var("S3_CDN_ENDPOINT")]
        self.__acl = app.config[self._env_var("ACL")]
        self.__session = boto3.session.Session()
        self._client = self.__session.client(
            "s3",
            region_name=app.config[self._env_var("S3_REGION")],
            endpoint_url=app.config[self._env_var("S3_ENDPOINT")],
            aws_access_key_id=app.config[self._env_var("S3_ACCESS_KEY")],
            aws_secret_access_key=app.config[self._env_var("S3_SECRET_KEY")],
            config=BotoConfig(signature_version="s3v4"),
        )

        self.__init_app(app)

    def __init_app(self, app: Flask) -> None:
        app.url_build_error_handlers.append(self.__url_build_error_handler)

    def __url_build_error_handler(
        self, error: BuildError, endpoint: str, values: Mapping[str, Any]
    ) -> Optional[str]:
        match endpoint:
            case "assets.item":
                endpoint = self.__cdn_endpoint
                if not endpoint.endswith("/"):
                    endpoint += "/"
                if (path := values.get("path")) is None:
                    raise BuildError("Endpoint assets.item missing value 'path'")
                return endpoint + path
            case _:
                raise NotImplementedError("Unreachable code")

    @staticmethod
    def mime_type(path: str) -> str:
        (typ, _) = mimetypes.guess_type(path)
        return typ or "binary/octet-stream"

    def _put(self, path: str, readable: IOBase) -> None:
        self._client.put_object(
            Bucket=self.__bucket,
            Key=path,
            Body=readable,
            ContentType=self.mime_type(path),
            ACL=self.__acl,
        )

    def _serve(self, path: str) -> Response:
        url = self._client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.__bucket,
                "Key": path,
                # "ResponseContentType": self.mime_type(path),
            },
            ExpiresIn=3600,
        )
        return redirect(url)


class BlobStorage(StorageBase):
    """
    Config options:
    - BLOB_STORAGE_DRIVER
    """

    def init_app(self, app: Flask) -> None:
        ext_name = self._ext_name()
        if ext_name in app.extensions:
            raise RuntimeError(f"Extension already loaded: {ext_name}")

        driver: Optional[StorageDriver]
        match app.config.get(self._env_var("DRIVER")) or None:
            case "file-system":
                driver = FsDriver(app, self._config_prefix)
            case "s3":
                driver = S3Driver(app, self._config_prefix)
            case None:
                driver = None
            case x:
                raise ValueError(f"Unknown storage driver: {x!r}")

        app.extensions[ext_name] = driver

    @property
    def _driver(self) -> StorageDriver:
        if driver := current_app.extensions[self._ext_name()]:
            return driver
        raise RuntimeError("No storage driver was configured")

    @staticmethod
    def _encrypted_file_path(file: FileUpload) -> str:
        return f"/messsages/{file.message_id}/encrypted-file/{file.id}.gpg"

    def put_encrypted_file(self, file: FileUpload, readable: IOBase) -> None:
        self._driver._put(self._encrypted_file_path(file), readable)

    def serve_encrypted_file(self, file: FileUpload) -> Response:
        return self._driver._serve(self._encrypted_file_path(file))


private_store = BlobStorage("PRIVATE")
