import mimetypes
import os
import shutil
from io import IOBase
from pathlib import Path
from typing import Any, Mapping, Optional

import boto3
from botocore.config import Config as BotoConfig
from flask import Blueprint, Flask, Response, current_app, send_from_directory
from werkzeug.routing import BuildError


class StorageBase:
    __NAME_BASE = "BLOB_STORAGE"
    _BLUEPRINT: Optional[Blueprint] = None

    def __init__(self, config_prefix: Optional[str] = None) -> None:
        self._config_prefix = config_prefix
        StorageBase._BLUEPRINT = Blueprint("assets", __file__)

    @classmethod
    def _blueprint(cls) -> Blueprint:
        if bp := cls._BLUEPRINT:
            return bp
        raise RuntimeError(f"{StorageBase.__name__} blueprint not initialized")

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
    def put(self, path: str, reable: IOBase) -> None:
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

        self.__init_app()

    def __init_app(self) -> None:
        bp = StorageBase._blueprint()

        @bp.route("/<path:path>")
        def item(path: str) -> Response:
            return send_from_directory(self.__root, path)

    def __full_path(self, path: str) -> Path:
        full_path = self.__root / path
        if full_path.absolute() != full_path:
            raise ValueError(f"Path {full_path!r} was not absolute")
        return full_path

    def put(self, path: str, readable: IOBase) -> None:
        full_path = self.__full_path(path)
        # TODO make and check permissions
        os.makedirs(full_path.parent, exist_ok=True)
        with open(full_path, "wb") as f:
            shutil.copyfileobj(readable, f)


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

    def put(self, path: str, readable: IOBase) -> None:
        (typ, _) = mimetypes.guess_type(path)
        self._client.put_object(
            Bucket=self.__bucket,
            Key=path,
            Body=readable,
            ContentType=typ or "binary/octet-stream",
            ACL=self.__acl,
        )


class BlobStorage(StorageBase):
    """
    Config options:
    - BLOB_STORAGE_DRIVER
    """

    def init_app(self, app: Flask) -> None:
        ext_name = self._ext_name()
        if ext_name in app.extensions:
            raise RuntimeError(f"Extension already loaded: {ext_name}")

        driver: StorageDriver
        match app.config[self._env_var("DRIVER")]:
            case "file-system":
                driver = FsDriver(app, self._config_prefix)
            case "s3":
                driver = S3Driver(app, self._config_prefix)
            case x:
                raise ValueError(f"Unknown storage driver: {x}")
        app.extensions[ext_name] = driver

    @classmethod
    def finalize(cls, app: Flask) -> None:
        if StorageBase._BLUEPRINT is not None:
            app.register_blueprint(StorageBase._BLUEPRINT, url_prefix="/assets")

    @property
    def _driver(self) -> StorageDriver:
        return current_app.extensions[self._ext_name()]

    def put(self, path: str, readable: IOBase) -> None:
        self._driver.put(path, readable)


private_store = BlobStorage("PRIVATE")
