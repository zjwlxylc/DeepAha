from hashlib import sha256
from unicodedata import normalize
from urllib.parse import urlsplit, urlunsplit

from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.opportunities.types import UNSET, OpportunityPatch


def normalize_identity_text(value: str) -> str:
    return " ".join(normalize("NFC", value).strip().casefold().split())


def normalize_official_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("official URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("official URL must not contain credentials")

    host = parsed.hostname.casefold().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


def stable_public_id_for_key(identity_key: str) -> str:
    digest = sha256(f"deepaha:opportunity:v0.3:{identity_key}".encode()).hexdigest()
    return f"opp_{digest[:32]}"


def weak_fingerprint(facts: OpportunityPatch) -> str | None:
    if (
        facts.type is UNSET
        or facts.canonical_title is UNSET
        or facts.issuer_name is UNSET
        or not isinstance(facts.type, OpportunityTypeV02)
        or not isinstance(facts.canonical_title, str)
        or not isinstance(facts.issuer_name, str)
        or not normalize_identity_text(facts.canonical_title)
        or not normalize_identity_text(facts.issuer_name)
    ):
        return None
    jurisdiction = (
        normalize_identity_text(facts.jurisdiction) if isinstance(facts.jurisdiction, str) else ""
    )
    components = (
        facts.type.value,
        normalize_identity_text(facts.issuer_name),
        normalize_identity_text(facts.canonical_title),
        jurisdiction,
    )
    return f"weak:{sha256(chr(31).join(components).encode()).hexdigest()}"


__all__ = [
    "normalize_identity_text",
    "normalize_official_url",
    "stable_public_id_for_key",
    "weak_fingerprint",
]
