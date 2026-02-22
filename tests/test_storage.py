import os
import random
import string
from io import BytesIO
from pathlib import Path
from typing import Callable, Generator, Mapping
from unittest.mock import MagicMock, Mock

import pytest
import requests
from _pytest._py.path import LocalPath
from flask import Flask
from pytest_mock import MockFixture
from werkzeug.exceptions import HTTPException, NotFound

from hushline.storage import BlobStorage, FsDriver, S3Driver, StorageDriver, public_store

PATH = "data.bin"

pytestmark = pytest.mark.filterwarnings(
    "ignore:datetime.datetime.utcnow\\(\\) is deprecated.*:DeprecationWarning:botocore.auth"
)


def mock_drivers(skip: type, mocker: MockFixture) -> None:
    for attr in ["put", "delete", "serve"]:
        for subclass in StorageDriver.__subclasses__():
            if subclass != skip:
                mocker.patch.object(
                    subclass,
                    attr,
                    Mock(
                        side_effect=Exception(
                            f"{subclass.__name__}.{attr} should not have been called"
                        )
                    ),
                )


class TestFsDriver:
    @pytest.fixture()
    def env_var_modifier(self, tmpdir: LocalPath) -> Callable[[MockFixture], None]:
        def modifier(mocker: MockFixture) -> None:
            mocker.patch.dict(
                os.environ,
                {
                    "BLOB_STORAGE_PUBLIC_DRIVER": "file-system",
                    "BLOB_STORAGE_PUBLIC_FS_ROOT": str(tmpdir),
                },
            )

            mock_drivers(FsDriver, mocker)

        return modifier

    def test_put_and_serve(self, app: Flask) -> None:
        data = b"waffles"
        public_store.put(PATH, BytesIO(data))

        with app.test_request_context():
            resp = public_store.serve(PATH)
        assert resp.status_code == 200

        resp.direct_passthrough = False
        assert resp.data == data

    def test_put_and_delete(self, app: Flask) -> None:
        public_store.put(PATH, BytesIO(b"waffles"))
        public_store.delete(PATH)

        with app.test_request_context(), pytest.raises(NotFound):
            public_store.serve(PATH)


class TestS3Driver:
    @property
    def static_configs(self) -> Mapping[str, str]:
        return {
            "BLOB_STORAGE_PUBLIC_DRIVER": "s3",
            "BLOB_STORAGE_PUBLIC_S3_REGION": "us-east-1",
            "BLOB_STORAGE_PUBLIC_S3_ENDPOINT": "http://blob-storage:4566/",
            "BLOB_STORAGE_PUBLIC_S3_ACCESS_KEY": "test",
            "BLOB_STORAGE_PUBLIC_S3_SECRET_KEY": "test",
        }

    @pytest.fixture()
    def env_var_modifier(self, tmpdir: LocalPath, bucket: str) -> Callable[[MockFixture], None]:
        def modifier(mocker: MockFixture) -> None:
            mocker.patch.dict(
                os.environ,
                {
                    "BLOB_STORAGE_PUBLIC_S3_BUCKET": bucket,
                    "BLOB_STORAGE_PUBLIC_S3_CDN_ENDPOINT": f"http://blob-storage:4566/{bucket}/",
                    **self.static_configs,
                },
            )

            mock_drivers(S3Driver, mocker)

        return modifier

    @pytest.fixture(autouse=True)
    def bucket(self) -> Generator[str, None, None]:
        bucket = "".join(random.choice(string.ascii_lowercase) for _ in range(12))

        mocked_app = MagicMock()
        mocked_app.config = dict(
            BLOB_STORAGE_PUBLIC_S3_BUCKET="",
            BLOB_STORAGE_PUBLIC_S3_CDN_ENDPOINT="",
            **self.static_configs,
        )
        driver = S3Driver(mocked_app, "PUBLIC")
        client = driver._client

        client.create_bucket(Bucket=bucket)

        yield bucket

        while True:
            resp = client.list_objects_v2(Bucket=bucket)
            if resp["KeyCount"] == 0:
                break
            client.delete_objects(
                Bucket=bucket, Delete={"Objects": [{"Key": x["Key"]} for x in resp["Contents"]]}
            )
        client.delete_bucket(Bucket=bucket)

    def test_put_and_serve(self, app: Flask) -> None:
        data = b"waffles"
        public_store.put(PATH, BytesIO(data))

        with app.test_request_context():
            resp = public_store.serve(PATH)
        assert resp.status_code == 302

        location = resp.headers["location"]

        s3_resp = requests.get(location, timeout=2)
        assert s3_resp.status_code == 200
        assert s3_resp.content == data

    def test_put_and_delete(self, app: Flask) -> None:
        public_store.put(PATH, BytesIO(b"waffles"))
        public_store.delete(PATH)

        with app.test_request_context():
            resp = public_store.serve(PATH)
        assert resp.status_code == 302

        s3_resp = requests.get(resp.headers["location"], timeout=2)
        assert s3_resp.status_code == 404


def test_storage_driver_methods_raise_not_implemented() -> None:
    driver = StorageDriver()
    with pytest.raises(NotImplementedError):
        driver.put(PATH, BytesIO(b"x"))
    with pytest.raises(NotImplementedError):
        driver.delete(PATH)
    with pytest.raises(NotImplementedError):
        driver.serve(PATH)


def test_fs_driver_rejects_relative_root() -> None:
    app = Flask(__name__)
    app.config["BLOB_STORAGE_FS_ROOT"] = "relative/path"
    with pytest.raises(ValueError, match="not absolute"):
        FsDriver(app)


def test_fs_driver_rejects_non_absolute_full_path(tmpdir: LocalPath) -> None:
    app = Flask(__name__)
    app.config["BLOB_STORAGE_FS_ROOT"] = str(tmpdir)
    driver = FsDriver(app)
    setattr(driver, "_FsDriver__root", Path("relative/root"))
    with pytest.raises(ValueError, match="not absolute"):
        driver.put("escape.bin", BytesIO(b"x"))


def test_fs_driver_rejects_windows_reserved_device_names(tmpdir: LocalPath) -> None:
    app = Flask(__name__)
    app.config["BLOB_STORAGE_FS_ROOT"] = str(tmpdir)
    driver = FsDriver(app)

    with pytest.raises(ValueError, match="not allowed"):
        driver.put("nested/CON.txt", BytesIO(b"x"))
    with pytest.raises(ValueError, match="not allowed"):
        driver.delete("AUX/report.txt")
    with pytest.raises(ValueError, match="not allowed"), app.test_request_context():
        driver.serve("docs/PRN.txt")


def test_s3_driver_private_serve_uses_presigned_url(mocker: MockFixture) -> None:
    app = MagicMock()
    app.config = {
        "BLOB_STORAGE_PRIVATE_S3_BUCKET": "bucket",
        "BLOB_STORAGE_PRIVATE_S3_CDN_ENDPOINT": "https://cdn.example",
        "BLOB_STORAGE_PRIVATE_S3_REGION": "us-east-1",
        "BLOB_STORAGE_PRIVATE_S3_ENDPOINT": "https://s3.example",
        "BLOB_STORAGE_PRIVATE_S3_ACCESS_KEY": "ak",
        "BLOB_STORAGE_PRIVATE_S3_SECRET_KEY": "sk",
    }
    fake_client = MagicMock()
    fake_client.generate_presigned_url.return_value = "https://signed.example/object"
    mocker.patch("hushline.storage.boto3.session.Session.client", return_value=fake_client)

    driver = S3Driver(app, "PRIVATE", is_public=False)
    response = driver.serve("object.bin")

    assert response.status_code == 302
    assert response.location == "https://signed.example/object"
    fake_client.generate_presigned_url.assert_called_once()


def test_blob_storage_init_rejects_unknown_driver() -> None:
    app = Flask(__name__)
    app.config["BLOB_STORAGE_DRIVER"] = "bad-driver"
    store = BlobStorage()
    with pytest.raises(ValueError, match="Unknown storage driver"):
        store.init_app(app)


def test_blob_storage_init_rejects_double_registration() -> None:
    app = Flask(__name__)
    app.config["BLOB_STORAGE_DRIVER"] = "none"
    store = BlobStorage()
    store.init_app(app)

    with pytest.raises(RuntimeError, match="Extension already loaded"):
        store.init_app(app)


def test_blob_storage_abort_when_driver_not_configured() -> None:
    app = Flask(__name__)
    app.extensions["BLOB_STORAGE"] = None
    store = BlobStorage()

    with app.app_context(), pytest.raises(HTTPException) as exc:
        store.put(PATH, BytesIO(b"data"))
    assert exc.value.code == 503
