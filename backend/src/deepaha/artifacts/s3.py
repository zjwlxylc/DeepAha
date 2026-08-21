from hashlib import sha256 as calculate_sha256
from typing import cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client
from mypy_boto3_s3.literals import BucketLocationConstraintType

from deepaha.artifacts.object_store import ObjectIntegrityError, ObjectMetadata
from deepaha.core.settings import Settings


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        if settings.object_store_access_key is None or settings.object_store_secret_key is None:
            raise ValueError("object-store access and secret keys are required")

        self._bucket = settings.object_store_bucket
        self._region = settings.object_store_region
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=str(settings.object_store_endpoint),
            region_name=settings.object_store_region,
            aws_access_key_id=settings.object_store_access_key,
            aws_secret_access_key=settings.object_store_secret_key.get_secret_value(),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except ClientError as error:
            if self._error_status(error) != 404:
                raise

        try:
            if self._region == "us-east-1":
                self._client.create_bucket(Bucket=self._bucket)
            else:
                self._client.create_bucket(
                    Bucket=self._bucket,
                    CreateBucketConfiguration={
                        "LocationConstraint": cast(
                            BucketLocationConstraintType,
                            self._region,
                        )
                    },
                )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
                raise

    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata:
        calculated = calculate_sha256(content).hexdigest()
        if calculated != sha256:
            raise ObjectIntegrityError("caller-supplied SHA-256 does not match object bytes")

        try:
            if media_type is None:
                self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    ContentLength=len(content),
                    IfNoneMatch="*",
                    Metadata={"sha256": sha256},
                )
            else:
                self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    ContentLength=len(content),
                    ContentType=media_type,
                    IfNoneMatch="*",
                    Metadata={"sha256": sha256},
                )
        except ClientError as error:
            if not self._is_conditional_conflict(error):
                raise
            existing = self.stat(key=key)
            if existing.byte_size != len(content) or existing.sha256 != sha256:
                raise ObjectIntegrityError(
                    "existing object does not match requested size and SHA-256"
                ) from error
            return existing

        return self.stat(key=key)

    def get_bytes(self, *, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        content = response["Body"].read()
        expected = response.get("Metadata", {}).get("sha256")
        calculated = calculate_sha256(content).hexdigest()
        if expected is None or calculated != expected:
            raise ObjectIntegrityError("downloaded object does not match stored SHA-256")
        return content

    def stat(self, *, key: str) -> ObjectMetadata:
        response = self._client.head_object(Bucket=self._bucket, Key=key)
        digest = response.get("Metadata", {}).get("sha256")
        if digest is None:
            raise ObjectIntegrityError("existing object has no stored SHA-256")
        return ObjectMetadata(
            bucket=self._bucket,
            key=key,
            byte_size=response["ContentLength"],
            sha256=digest,
            media_type=response.get("ContentType"),
        )

    @staticmethod
    def _error_status(error: ClientError) -> int | None:
        return error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

    @classmethod
    def _is_conditional_conflict(cls, error: ClientError) -> bool:
        code = error.response.get("Error", {}).get("Code")
        return cls._error_status(error) in {409, 412} or code in {
            "ConditionalRequestConflict",
            "PreconditionFailed",
        }
