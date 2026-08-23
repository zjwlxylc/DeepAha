import re
import unicodedata

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_PARSER_COMPONENT_PATTERN = re.compile(r"[a-z0-9._-]+")


def normalize_text(value: str) -> str:
    """Apply only the Phase 2 loss-minimizing text normalization rules."""
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    result: list[str] = []
    previous_blank = False
    for raw_line in normalized.split("\n"):
        line = raw_line.rstrip(" \t")
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        result.append(line)
        previous_blank = is_blank
    return "\n".join(result)


def build_derived_text_key(
    artifact_sha256: str,
    parser_name: str,
    parser_version: str,
) -> str:
    if _SHA256_PATTERN.fullmatch(artifact_sha256) is None:
        raise ValueError("artifact SHA-256 must be 64 lowercase hexadecimal characters")
    if any(
        _PARSER_COMPONENT_PATTERN.fullmatch(component) is None
        for component in (parser_name, parser_version)
    ):
        raise ValueError("parser name and version must contain only [a-z0-9._-]")
    return f"derived/documents/{artifact_sha256}/{parser_name}/{parser_version}/text.txt"
