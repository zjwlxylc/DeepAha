from dataclasses import dataclass
from typing import Protocol


class ObjectIntegrityError(RuntimeError):
    """Raised when object bytes and their integrity metadata disagree."""


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    bucket: str
    key: str
    byte_size: int
    sha256: str
    media_type: str | None


class ObjectStore(Protocol):
    def ensure_bucket(self) -> None:
        raise NotImplementedError

    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata:
        raise NotImplementedError

    def get_bytes(self, *, key: str) -> bytes:
        raise NotImplementedError

    def stat(self, *, key: str) -> ObjectMetadata:
        raise NotImplementedError
