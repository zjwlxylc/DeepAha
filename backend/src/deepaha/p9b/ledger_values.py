import re
from typing import Final, Literal

GatewayStringKind = Literal[
    "IDENTIFIER",
    "PROVIDER_RESPONSE_ID",
    "STORAGE_BUCKET",
    "OBJECT_KEY",
    "ERROR_CODE",
    "SHA256",
]

_IDENTIFIER: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")
_PROVIDER_RESPONSE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]*$")
_STORAGE_BUCKET: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
_ERROR_CODE: Final = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_CREDENTIAL_PATTERNS: Final = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:^|[^a-z0-9_])(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=]",
        r"(?:^|[^a-z0-9_])(?:bearer|basic)\s+[a-z0-9._~+/\-]{8,}=*",
        r"(?:^|[^a-z0-9_])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|password|credential)\s*[:=]",
        r"(?:^|[^a-z0-9_])sk-(?:proj-)?[a-z0-9_-]{20,}",
        r"(?:^|[^a-z0-9_])xox[baprs]-[a-z0-9-]{20,}",
        r"(?:^|[^a-z0-9_])gh[pousr]_[a-z0-9]{20,}",
        r"(?:^|[^a-z0-9_])glpat-[a-z0-9_-]{20,}",
        r"(?:^|[^a-z0-9_])akia[0-9a-z]{16}(?:[^0-9a-z]|$)",
        r"(?:^|[^a-z0-9_])aiza[0-9a-z_-]{30,}",
        r"(?:^|[^a-z0-9_])(?:sk|rk)_(?:live|test)_[a-z0-9]{16,}",
        r"(?:^|[^a-z0-9_])whsec_[a-z0-9]{16,}",
        r"(?:^|[^a-z0-9_-])eyj[a-z0-9_-]{8,}\.eyj[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}",
        r"-----begin [a-z0-9 ]*private key-----",
        r"[?&](?:access_token|api[_-]?key|token|signature|x-amz-credential|x-amz-signature|sig|secret|password)=",
        r"[a-z][a-z0-9+.-]*://[^/?#\s]+:[^@/?#\s]+@",
    )
)


def contains_credential_material(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value) or any(
        pattern.search(value) is not None for pattern in _CREDENTIAL_PATTERNS
    )


def is_gateway_string_value_allowed(value: str, kind: str) -> bool:
    if not value or contains_credential_material(value):
        return False
    if kind == "IDENTIFIER":
        return len(value) <= 128 and _IDENTIFIER.fullmatch(value) is not None
    if kind == "PROVIDER_RESPONSE_ID":
        return len(value) <= 256 and _PROVIDER_RESPONSE_ID.fullmatch(value) is not None
    if kind == "STORAGE_BUCKET":
        return len(value) <= 128 and _STORAGE_BUCKET.fullmatch(value) is not None
    if kind == "OBJECT_KEY":
        segments = value.split("/")
        return (
            len(value) <= 512
            and value == value.strip()
            and not value.startswith(("/", "\\"))
            and "\\" not in value
            and "://" not in value
            and "?" not in value
            and "#" not in value
            and all(segment not in {"", ".", ".."} for segment in segments)
        )
    if kind == "ERROR_CODE":
        return len(value) <= 64 and _ERROR_CODE.fullmatch(value) is not None
    if kind == "SHA256":
        return _SHA256.fullmatch(value) is not None
    return False


def require_gateway_string_value(
    value: str,
    kind: GatewayStringKind,
    *,
    field_name: str,
) -> str:
    if not is_gateway_string_value_allowed(value, kind):
        raise ValueError(f"{field_name} violates the Gateway string-value contract")
    return value


def require_identifier(value: str) -> str:
    return require_gateway_string_value(value, "IDENTIFIER", field_name="identifier")


def require_provider_response_id(value: str) -> str:
    return require_gateway_string_value(
        value,
        "PROVIDER_RESPONSE_ID",
        field_name="provider_response_id",
    )


def require_storage_bucket(value: str) -> str:
    return require_gateway_string_value(value, "STORAGE_BUCKET", field_name="storage_bucket")


def require_object_key(value: str) -> str:
    return require_gateway_string_value(value, "OBJECT_KEY", field_name="object_key")


def require_error_code(value: str) -> str:
    return require_gateway_string_value(value, "ERROR_CODE", field_name="error_code")


def require_sha256(value: str) -> str:
    return require_gateway_string_value(value, "SHA256", field_name="sha256")


__all__ = [
    "GatewayStringKind",
    "contains_credential_material",
    "is_gateway_string_value_allowed",
    "require_error_code",
    "require_gateway_string_value",
    "require_identifier",
    "require_object_key",
    "require_provider_response_id",
    "require_sha256",
    "require_storage_bucket",
]
