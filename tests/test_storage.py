import os
import random
import string
from io import BytesIO
from typing import Callable, Generator, Mapping
from unittest.mock import MagicMock, Mock

import pytest
import requests
from _pytest._py.path import LocalPath
from flask import Flask
from pytest_mock import MockFixture
from werkzeug.exceptions import NotFound

from hushline.storage import FsDriver, S3Driver, StorageDriver, public_store

PATH = "data.bin"


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
                    "BLOB_STORAGE_PUBLIC_S3_CDN_ENDPOINT": f"http://localhost:4566/{bucket}/",
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
