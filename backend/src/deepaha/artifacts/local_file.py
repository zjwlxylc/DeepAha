import json
import os
import re
from contextlib import suppress
from hashlib import sha256 as calculate_sha256
from pathlib import Path, PurePosixPath
from uuid import uuid4

from deepaha.artifacts.object_store import ObjectIntegrityError, ObjectMetadata

_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class LocalFileObjectStore:
    def __init__(self, *, root: Path, bucket: str) -> None:
        if not _BUCKET_PATTERN.fullmatch(bucket):
            raise ValueError("bucket name is invalid")
        self._root = root.resolve()
        self._bucket = bucket
        self._bucket_root = self._root / bucket
        self._object_root = self._bucket_root / "objects"
        self._metadata_root = self._bucket_root / "metadata"
        self._lock_root = self._bucket_root / ".locks"

    def ensure_bucket(self) -> None:
        for path in (self._object_root, self._metadata_root, self._lock_root):
            path.mkdir(parents=True, exist_ok=True)

    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata:
        parts = self._key_parts(key)
        calculated = calculate_sha256(content).hexdigest()
        if calculated != sha256:
            raise ObjectIntegrityError("caller-supplied SHA-256 does not match object bytes")
        self.ensure_bucket()
        object_path, metadata_path = self._paths(parts)
        lock_path = self._lock_root / calculate_sha256(key.encode("utf-8")).hexdigest()
        lock_descriptor = self._acquire_lock(lock_path)
        try:
            if object_path.exists() or metadata_path.exists():
                existing = self._load_metadata(key=key, parts=parts)
                if existing.byte_size != len(content) or existing.sha256 != sha256:
                    raise ObjectIntegrityError(
                        "existing object does not match requested size and SHA-256"
                    )
                return existing
            return self._write_new(
                key=key,
                parts=parts,
                content=content,
                media_type=media_type,
                digest=sha256,
            )
        finally:
            self._release_lock(lock_descriptor)

    def get_bytes(self, *, key: str) -> bytes:
        parts = self._key_parts(key)
        metadata = self._load_metadata(key=key, parts=parts)
        object_path, _metadata_path = self._paths(parts)
        try:
            content = object_path.read_bytes()
        except OSError as error:
            raise ObjectIntegrityError("stored object bytes are unavailable") from error
        if calculate_sha256(content).hexdigest() != metadata.sha256:
            raise ObjectIntegrityError("object bytes do not match stored SHA-256")
        return content

    def stat(self, *, key: str) -> ObjectMetadata:
        parts = self._key_parts(key)
        return self._load_metadata(key=key, parts=parts)

    def stat_if_present(self, *, key: str) -> ObjectMetadata | None:
        parts = self._key_parts(key)
        object_path, metadata_path = self._paths(parts)
        if not object_path.exists() and not metadata_path.exists():
            return None
        return self._load_metadata(key=key, parts=parts)

    def delete_if_matches(self, *, key: str, sha256: str) -> bool:
        parts = self._key_parts(key)
        self.ensure_bucket()
        object_path, metadata_path = self._paths(parts)
        lock_path = self._lock_root / calculate_sha256(key.encode("utf-8")).hexdigest()
        lock_descriptor = self._acquire_lock(lock_path)
        try:
            if not object_path.exists() and not metadata_path.exists():
                return False
            metadata = self._load_metadata(key=key, parts=parts)
            if metadata.sha256 != sha256:
                raise ObjectIntegrityError("refusing to delete an object with a different SHA-256")
            object_path.unlink()
            metadata_path.unlink()
            return True
        except OSError as error:
            raise ObjectIntegrityError("compensating object deletion failed") from error
        finally:
            self._release_lock(lock_descriptor)

    def _write_new(
        self,
        *,
        key: str,
        parts: tuple[str, ...],
        content: bytes,
        media_type: str | None,
        digest: str,
    ) -> ObjectMetadata:
        object_path, metadata_path = self._paths(parts)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = uuid4().hex
        object_temporary = object_path.with_name(f".{object_path.name}.{suffix}.tmp")
        metadata_temporary = metadata_path.with_name(f".{metadata_path.name}.{suffix}.tmp")
        metadata = ObjectMetadata(
            bucket=self._bucket,
            key=key,
            byte_size=len(content),
            sha256=digest,
            media_type=media_type,
        )
        metadata_content = json.dumps(
            {
                "bucket": metadata.bucket,
                "key": metadata.key,
                "byte_size": metadata.byte_size,
                "sha256": metadata.sha256,
                "media_type": metadata.media_type,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        object_published = False
        try:
            self._write_temporary(object_temporary, content)
            self._write_temporary(metadata_temporary, metadata_content)
            os.replace(object_temporary, object_path)
            object_published = True
            os.replace(metadata_temporary, metadata_path)
        except OSError as error:
            if object_published:
                with suppress(OSError):
                    object_path.unlink()
            raise ObjectIntegrityError(
                "object publish failed without leaving partial data"
            ) from error
        finally:
            with suppress(OSError):
                object_temporary.unlink(missing_ok=True)
            with suppress(OSError):
                metadata_temporary.unlink(missing_ok=True)
        return self._load_metadata(key=key, parts=parts)

    def _load_metadata(self, *, key: str, parts: tuple[str, ...]) -> ObjectMetadata:
        object_path, metadata_path = self._paths(parts)
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = ObjectMetadata(
                bucket=raw["bucket"],
                key=raw["key"],
                byte_size=raw["byte_size"],
                sha256=raw["sha256"],
                media_type=raw["media_type"],
            )
            content = object_path.read_bytes()
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ObjectIntegrityError(
                "stored object metadata is unavailable or invalid"
            ) from error
        if (
            metadata.bucket != self._bucket
            or metadata.key != key
            or not isinstance(metadata.byte_size, int)
            or metadata.byte_size < 0
            or not isinstance(metadata.sha256, str)
            or len(metadata.sha256) != 64
            or any(character not in "0123456789abcdef" for character in metadata.sha256)
            or metadata.media_type is not None
            and not isinstance(metadata.media_type, str)
        ):
            raise ObjectIntegrityError("stored object metadata is invalid")
        actual_digest = calculate_sha256(content).hexdigest()
        if metadata.byte_size != len(content) or metadata.sha256 != actual_digest:
            raise ObjectIntegrityError("object bytes do not match stored SHA-256")
        return metadata

    @staticmethod
    def _write_temporary(path: Path, content: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _acquire_lock(path: Path) -> int:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]
                    descriptor,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
                )
            return descriptor
        except OSError as error:
            if "descriptor" in locals():
                os.close(descriptor)
            raise ObjectIntegrityError("object write is already in progress") from error

    @staticmethod
    def _release_lock(descriptor: int) -> None:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]
                    descriptor,
                    fcntl.LOCK_UN,  # type: ignore[attr-defined]
                )
        finally:
            os.close(descriptor)

    def _paths(self, parts: tuple[str, ...]) -> tuple[Path, Path]:
        object_path = self._object_root.joinpath(*parts)
        metadata_base = self._metadata_root.joinpath(*parts)
        metadata_path = metadata_base.with_name(f"{metadata_base.name}.json")
        return object_path, metadata_path

    @staticmethod
    def _key_parts(key: str) -> tuple[str, ...]:
        if not key or "\\" in key or "\x00" in key or ":" in key or key.startswith("/"):
            raise ValueError("object key must be a canonical relative path")
        parts = tuple(key.split("/"))
        if any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts):
            raise ValueError("object key must be a canonical relative path")
        if PurePosixPath(*parts).as_posix() != key:
            raise ValueError("object key must be a canonical relative path")
        return parts


__all__ = ["LocalFileObjectStore"]
