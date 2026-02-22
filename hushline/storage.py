import contextlib
import mimetypes
import os
import shutil
from io import IOBase
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from flask import Blueprint, Flask, abort, current_app, redirect, send_from_directory
from werkzeug.wrappers.response import Response


def create_blueprint() -> Blueprint:
    bp = Blueprint("storage", __name__, url_prefix="/assets")

    @bp.route("/public/<path:path>")
    def public(path: str) -> Response:
        return public_store.serve(path)

    return bp


class StorageBase:
    __NAME_BASE = "BLOB_STORAGE"

    def __init__(self, config_prefix: Optional[str] = None, is_public: bool = False) -> None:
        self._config_prefix = config_prefix
        self._is_public = is_public

    def _config_name(self, name: str) -> str:
        env_var = self.__NAME_BASE
        if self._config_prefix:
            env_var += "_" + self._config_prefix
        return f"{env_var}_{name}"

    def _ext_name(self) -> str:
        if self._config_prefix:
            return f"{self.__NAME_BASE}_{self._config_prefix}"
        return self.__NAME_BASE


class StorageDriver(StorageBase):
    def put(self, path: str, readable: IOBase) -> None:
        raise NotImplementedError

    def delete(self, path: str) -> None:
        raise NotImplementedError

    def serve(self, path: str) -> Response:
        raise NotImplementedError


class FsDriver(StorageDriver):
    """
    Config options:
    - BLOB_STORAGE_FS_ROOT
    """

    _WINDOWS_RESERVED_DEVICE_NAMES = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    def __init__(
        self, app: Flask, config_prefix: Optional[str] = None, is_public: bool = False
    ) -> None:
        super().__init__(config_prefix, is_public)

        root = Path(app.config[self._config_name("FS_ROOT")])
        if root.absolute() != root:  # needed for security checks later
            raise ValueError(f"Path {root!r} was not absolute")
        self.__root = root

    def __reject_windows_device_path_segments(self, path: str) -> None:
        # Keep path safety consistent across platforms, including Windows-reserved device names.
        for segment in path.replace("\\", "/").split("/"):
            if not segment:
                continue

            normalized = segment.rstrip(" .")
            if not normalized:
                continue

            stem = normalized.split(".", 1)[0].upper()
            if stem in self._WINDOWS_RESERVED_DEVICE_NAMES:
                raise ValueError(f"Path segment {segment!r} is not allowed")

    def __full_path(self, path: str) -> Path:
        self.__reject_windows_device_path_segments(path)
        full_path = self.__root / path
        if full_path.absolute() != full_path:
            raise ValueError(f"Path {full_path!r} was not absolute")
        return full_path

    def put(self, path: str, readable: IOBase) -> None:
        readable.seek(0)
        full_path = self.__full_path(path)
        # TODO check and set permissions
        os.makedirs(full_path.parent, exist_ok=True)
        with open(full_path, "wb") as f:
            shutil.copyfileobj(readable, f)

    def delete(self, path: str) -> None:
        full_path = self.__full_path(path)
        with contextlib.suppress(FileNotFoundError):
            os.remove(full_path)

    def serve(self, path: str) -> Response:
        self.__reject_windows_device_path_segments(path)
        return send_from_directory(self.__root, path)


class S3Driver(StorageDriver):
    """Config options
    - BLOB_STORAGE_S3_REGION
    - BLOB_STORAGE_S3_ENDPOINT
    - BLOB_STORAGE_S3_ACCESS_KEY
    - BLOB_STORAGE_S3_SECRET_KEY
    - BLOB_STORAGE_S3_BUCKET
    - BLOB_STORAGE_S3_CDN_ENDPOINT
    """

    def __init__(
        self, app: Flask, config_prefix: Optional[str] = None, is_public: bool = False
    ) -> None:
        super().__init__(config_prefix, is_public)

        self.__bucket = app.config[self._config_name("S3_BUCKET")]
        self.__cdn_endpoint = app.config[self._config_name("S3_CDN_ENDPOINT")]
        self.__session = boto3.session.Session()
        self._client = self.__session.client(
            "s3",
            region_name=app.config[self._config_name("S3_REGION")],
            endpoint_url=app.config[self._config_name("S3_ENDPOINT")],
            aws_access_key_id=app.config[self._config_name("S3_ACCESS_KEY")],
            aws_secret_access_key=app.config[self._config_name("S3_SECRET_KEY")],
            config=BotoConfig(signature_version="s3v4"),
        )

    @staticmethod
    def mime_type(path: str) -> str:
        (typ, _) = mimetypes.guess_type(path)
        return typ or "binary/octet-stream"

    def put(self, path: str, readable: IOBase) -> None:
        self._client.put_object(
            Bucket=self.__bucket,
            Key=path,
            Body=readable,
            ContentType=self.mime_type(path),
            ACL="public-read" if self._is_public else "private",
        )

    def delete(self, path: str) -> None:
        self._client.delete_object(Bucket=self.__bucket, Key=path)

    def serve(self, path: str) -> Response:
        if self._is_public:
            url = (
                self.__cdn_endpoint
                + ("" if self.__cdn_endpoint.endswith("/") or path.startswith("/") else "/")
                + path
            )
        else:
            url = self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.__bucket,
                    "Key": path,
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
        match app.config.get(self._config_name("DRIVER")) or None:
            case "s3":
                driver = S3Driver(app, self._config_prefix, self._is_public)
            case "file-system":
                driver = FsDriver(app, self._config_prefix, self._is_public)
            case "none":
                driver = None
            case None:
                driver = None
            case x:
                raise ValueError(f"Unknown storage driver: {x!r}")

        app.extensions[ext_name] = driver

    @property
    def _driver(self) -> StorageDriver:
        if driver := current_app.extensions[self._ext_name()]:
            return driver
        current_app.logger.error("No storage driver was configured")
        abort(503)  # noqa: RET503

    def put(self, path: str, readable: IOBase) -> None:
        return self._driver.put(path, readable)

    def delete(self, path: str) -> None:
        return self._driver.delete(path)

    def serve(self, path: str) -> Response:
        return self._driver.serve(path)


public_store = BlobStorage("PUBLIC", is_public=True)
