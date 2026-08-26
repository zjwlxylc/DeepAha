import base64
import ctypes
import os
import subprocess
from collections.abc import Callable
from contextlib import suppress
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from deepaha.local_human_test.contracts import ProviderConfigSnapshot


class ProviderConfigError(RuntimeError):
    """A local Provider configuration boundary failed closed."""


class SecretProtector(Protocol):
    def protect(self, secret: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class DirectoryHardener(Protocol):
    def harden(self, path: Path) -> None: ...


class SaveProviderConfig(ProviderConfigSnapshot):
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if (
            not secret
            or len(secret) > 4096
            or secret != secret.strip()
            or any(character.isspace() or not character.isprintable() for character in secret)
        ):
            raise ValueError("Provider API key has an invalid shape")
        return value


class ProviderConfigStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configured: bool
    provider: str | None
    base_url: str | None
    protocol: str | None
    model_id: str | None
    model_snapshot: str | None
    provider_region: str | None
    zero_retention: bool | None
    training_use: bool | None
    supports_idempotency: bool | None
    egress_ready: bool
    updated_at: datetime | None


class ResolvedProviderConfig(ProviderConfigSnapshot):
    api_key: SecretStr


class _StoredProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.[01]$")
    provider: str
    base_url: str
    protocol: str
    model_id: str
    model_snapshot: str
    provider_region: str = "unknown"
    zero_retention: bool = False
    training_use: bool = True
    supports_idempotency: bool = False
    protected_api_key: str | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_public_configuration(self) -> Self:
        ProviderConfigSnapshot.model_validate(
            {
                "provider": self.provider,
                "base_url": self.base_url,
                "protocol": self.protocol,
                "model_id": self.model_id,
                "model_snapshot": self.model_snapshot,
                "provider_region": self.provider_region,
                "zero_retention": self.zero_retention,
                "training_use": self.training_use,
                "supports_idempotency": self.supports_idempotency,
            }
        )
        return self


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsDpapiProtector:
    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def protect(self, secret: bytes) -> bytes:
        return self._crypt(secret, protect=True)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._crypt(ciphertext, protect=False)

    def _crypt(self, content: bytes, *, protect: bool) -> bytes:
        if os.name != "nt":
            raise ProviderConfigError("Windows DPAPI is unavailable")
        if not content:
            raise ProviderConfigError("DPAPI input must not be empty")

        input_buffer = (ctypes.c_ubyte * len(content)).from_buffer_copy(content)
        input_blob = _DataBlob(len(content), input_buffer)
        output_blob = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        try:
            operation = (
                crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
            )
            succeeded = operation(
                ctypes.byref(input_blob),
                None,
                None,
                None,
                None,
                self._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output_blob),
            )
            if not succeeded:
                raise ProviderConfigError("Windows DPAPI operation failed")
            result = ctypes.string_at(output_blob.pbData, output_blob.cbData)
            return bytes(result)
        finally:
            ctypes.memset(input_buffer, 0, len(content))
            if output_blob.pbData:
                if not protect:
                    ctypes.memset(output_blob.pbData, 0, output_blob.cbData)
                kernel32.LocalFree(output_blob.pbData)


CommandRunner = Callable[[list[str]], tuple[int, str]]


def _run_command(arguments: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return completed.returncode, completed.stdout


class WindowsDirectoryHardener:
    def __init__(self, *, runner: CommandRunner = _run_command) -> None:
        self._runner = runner

    def harden(self, path: Path) -> None:
        identity_status, identity_output = self._runner(["whoami"])
        identity = identity_output.strip()
        if (
            identity_status != 0
            or not identity
            or any(character.isspace() for character in identity)
        ):
            raise ProviderConfigError("current Windows identity could not be resolved")
        status, _output = self._runner(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{identity}:(OI)(CI)(F)",
                "*S-1-5-18:(OI)(CI)(F)",
            ]
        )
        if status != 0:
            raise ProviderConfigError("permission hardening failed")


class LocalProviderConfigStore:
    _FILE_NAME = "provider.json"

    def __init__(
        self,
        *,
        root: Path,
        protector: SecretProtector,
        hardener: DirectoryHardener,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = root.resolve()
        self._protector = protector
        self._hardener = hardener
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def _path(self) -> Path:
        return self._root / self._FILE_NAME

    def save(self, command: SaveProviderConfig) -> ProviderConfigStatus:
        self._prepare_root()
        secret_buffer = bytearray(command.api_key.get_secret_value(), "utf-8")
        try:
            protected = self._protector.protect(bytes(secret_buffer))
        except Exception as error:
            raise ProviderConfigError("Provider secret protection failed") from error
        finally:
            secret_buffer[:] = b"\x00" * len(secret_buffer)

        payload = _StoredProviderConfig(
            schema_version="1.1",
            provider=command.provider,
            base_url=str(command.base_url).rstrip("/"),
            protocol=command.protocol,
            model_id=command.model_id,
            model_snapshot=command.model_snapshot,
            provider_region=command.provider_region,
            zero_retention=command.zero_retention,
            training_use=command.training_use,
            supports_idempotency=command.supports_idempotency,
            protected_api_key=base64.b64encode(protected).decode("ascii"),
            updated_at=self._clock(),
        )
        self._atomic_write(payload)
        return self._status_from(payload)

    def status(self) -> ProviderConfigStatus:
        if not self._path.exists():
            return ProviderConfigStatus(
                configured=False,
                provider=None,
                base_url=None,
                protocol=None,
                model_id=None,
                model_snapshot=None,
                provider_region=None,
                zero_retention=None,
                training_use=None,
                supports_idempotency=None,
                egress_ready=False,
                updated_at=None,
            )
        return self._status_from(self._read())

    def load_for_invocation(self) -> ResolvedProviderConfig:
        self._prepare_root()
        payload = self._read()
        if payload.protected_api_key is None:
            raise ProviderConfigError("Provider secret is not configured")
        try:
            ciphertext = base64.b64decode(payload.protected_api_key, validate=True)
            plaintext = bytearray(self._protector.unprotect(ciphertext))
            secret = plaintext.decode("utf-8")
        except Exception as error:
            raise ProviderConfigError("Provider secret could not be decrypted") from error
        finally:
            if "plaintext" in locals():
                plaintext[:] = b"\x00" * len(plaintext)
        return ResolvedProviderConfig.model_validate(
            {
                "provider": payload.provider,
                "base_url": payload.base_url,
                "protocol": payload.protocol,
                "model_id": payload.model_id,
                "model_snapshot": payload.model_snapshot,
                "provider_region": payload.provider_region,
                "zero_retention": payload.zero_retention,
                "training_use": payload.training_use,
                "supports_idempotency": payload.supports_idempotency,
                "api_key": SecretStr(secret),
            }
        )

    def delete_secret(self) -> ProviderConfigStatus:
        self._prepare_root()
        payload = self._read()
        without_secret = payload.model_copy(
            update={"protected_api_key": None, "updated_at": self._clock()}
        )
        self._atomic_write(without_secret)
        return self._status_from(without_secret)

    def _prepare_root(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._hardener.harden(self._root)
        except ProviderConfigError:
            raise
        except OSError as error:
            raise ProviderConfigError("Provider configuration directory is unavailable") from error

    def _read(self) -> _StoredProviderConfig:
        try:
            raw = self._path.read_text(encoding="utf-8")
            return _StoredProviderConfig.model_validate_json(raw)
        except (OSError, ValueError) as error:
            raise ProviderConfigError("Provider configuration is unreadable") from error

    def _atomic_write(self, payload: _StoredProviderConfig) -> None:
        temporary = self._path.with_name(f".{self._FILE_NAME}.{uuid4().hex}.tmp")
        content = payload.model_dump_json(exclude_none=True).encode("utf-8")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        except OSError as error:
            raise ProviderConfigError("Provider configuration write failed") from error
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _status_from(payload: _StoredProviderConfig) -> ProviderConfigStatus:
        return ProviderConfigStatus(
            configured=payload.protected_api_key is not None,
            provider=payload.provider,
            base_url=payload.base_url,
            protocol=payload.protocol,
            model_id=payload.model_id,
            model_snapshot=payload.model_snapshot,
            provider_region=payload.provider_region,
            zero_retention=payload.zero_retention,
            training_use=payload.training_use,
            supports_idempotency=payload.supports_idempotency,
            egress_ready=(
                payload.provider_region != "unknown"
                and payload.zero_retention
                and not payload.training_use
            ),
            updated_at=payload.updated_at,
        )


__all__ = [
    "DirectoryHardener",
    "LocalProviderConfigStore",
    "ProviderConfigError",
    "ProviderConfigStatus",
    "ResolvedProviderConfig",
    "SaveProviderConfig",
    "SecretProtector",
    "WindowsDirectoryHardener",
    "WindowsDpapiProtector",
]
