from hashlib import sha256

import boto3
import pytest
from botocore.config import Config
from mypy_boto3_s3 import S3Client

from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def object_store_settings() -> Settings:
    settings = Settings()
    if settings.object_store_access_key is None or settings.object_store_secret_key is None:
        pytest.fail("local object-store credentials are required for integration tests")
    return settings


@pytest.fixture(scope="module")
def raw_s3_client(object_store_settings: Settings) -> S3Client:
    assert object_store_settings.object_store_access_key is not None
    assert object_store_settings.object_store_secret_key is not None
    return boto3.client(
        "s3",
        endpoint_url=str(object_store_settings.object_store_endpoint),
        region_name=object_store_settings.object_store_region,
        aws_access_key_id=object_store_settings.object_store_access_key,
        aws_secret_access_key=object_store_settings.object_store_secret_key.get_secret_value(),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@pytest.fixture(scope="module")
def object_store(object_store_settings: Settings) -> S3ObjectStore:
    store = S3ObjectStore(object_store_settings)
    store.ensure_bucket()
    return store


def test_ensure_bucket_accepts_existing_owned_bucket(object_store: S3ObjectStore) -> None:
    object_store.ensure_bucket()


def test_put_if_absent_reuses_identical_object(object_store: S3ObjectStore) -> None:
    content = b"phase-1-raw-evidence"
    digest = sha256(content).hexdigest()
    key = f"raw/sha256/{digest[:2]}/{digest}"

    first = object_store.put_bytes_if_absent(
        key=key,
        content=content,
        media_type="application/octet-stream",
        sha256=digest,
    )
    second = object_store.put_bytes_if_absent(
        key=key,
        content=content,
        media_type="application/octet-stream",
        sha256=digest,
    )

    assert second == first
    assert object_store.get_bytes(key=key) == content
    assert object_store.stat(key=key) == first


def test_caller_supplied_hash_mismatch_is_rejected(object_store: S3ObjectStore) -> None:
    with pytest.raises(ObjectIntegrityError):
        object_store.put_bytes_if_absent(
            key="raw/sha256/00/" + "0" * 64,
            content=b"not-zero-hash",
            media_type="application/octet-stream",
            sha256="0" * 64,
        )


def test_existing_object_with_wrong_metadata_is_never_overwritten(
    object_store: S3ObjectStore,
    raw_s3_client: S3Client,
    object_store_settings: Settings,
) -> None:
    content = b"expected-content"
    digest = sha256(content).hexdigest()
    key = f"raw/sha256/{digest[:2]}/{digest}"
    raw_s3_client.put_object(
        Bucket=object_store_settings.object_store_bucket,
        Key=key,
        Body=content,
        ContentType="application/octet-stream",
        Metadata={"sha256": "f" * 64},
    )

    with pytest.raises(ObjectIntegrityError, match="existing object"):
        object_store.put_bytes_if_absent(
            key=key,
            content=content,
            media_type="application/octet-stream",
            sha256=digest,
        )

    response = raw_s3_client.get_object(
        Bucket=object_store_settings.object_store_bucket,
        Key=key,
    )
    assert response["Metadata"]["sha256"] == "f" * 64


def test_get_bytes_rejects_body_that_disagrees_with_metadata(
    object_store: S3ObjectStore,
    raw_s3_client: S3Client,
    object_store_settings: Settings,
) -> None:
    content = b"tampered-download"
    digest = sha256(content).hexdigest()
    key = f"raw/sha256/{digest[:2]}/{digest}"
    raw_s3_client.put_object(
        Bucket=object_store_settings.object_store_bucket,
        Key=key,
        Body=content,
        Metadata={"sha256": "f" * 64},
    )

    with pytest.raises(ObjectIntegrityError, match="downloaded object"):
        object_store.get_bytes(key=key)
