import json
import re
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

HASH_CONTRACT_VERSION = "p9b-canonical-json-sha256-v1"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class HashDomain(StrEnum):
    DOCUMENT_PARSE_KEY = "document_parse_key"
    CANONICAL_BUNDLE_HASH = "canonical_bundle_hash"
    SPLIT_MANIFEST_HASH = "split_manifest_hash"
    MEMBER_PROVENANCE_HASH = "member_provenance_hash"


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(domain: HashDomain, payload: object) -> str:
    return _canonical_hash_domain(domain.value, payload)


def _canonical_hash_domain(domain: str, payload: object) -> str:
    separator = f"deepaha:p9b:{domain}:{HASH_CONTRACT_VERSION}\0".encode()
    return sha256(separator + canonical_json_bytes(payload)).hexdigest()


def document_parse_key(
    *,
    artifact_id: UUID,
    artifact_sha256: str,
    parser_name: str,
    parser_version: str,
    parse_contract_version: str,
) -> str:
    if not _SHA256_PATTERN.fullmatch(artifact_sha256):
        raise ValueError("artifact_sha256 must be lowercase SHA-256")
    for label, value in (
        ("parser_name", parser_name),
        ("parser_version", parser_version),
        ("parse_contract_version", parse_contract_version),
    ):
        if not value.strip():
            raise ValueError(f"{label} must not be empty")
    return canonical_hash(
        HashDomain.DOCUMENT_PARSE_KEY,
        {
            "artifact_id": str(artifact_id),
            "artifact_sha256": artifact_sha256,
            "parse_contract_version": parse_contract_version,
            "parser_name": parser_name,
            "parser_version": parser_version,
        },
    )


def canonical_bundle_hash(payload: object) -> str:
    return canonical_hash(HashDomain.CANONICAL_BUNDLE_HASH, payload)


def split_manifest_hash(payload: object) -> str:
    return canonical_hash(HashDomain.SPLIT_MANIFEST_HASH, payload)


def member_provenance_hash(payload: object) -> str:
    return canonical_hash(HashDomain.MEMBER_PROVENANCE_HASH, payload)


def document_block_hash(payload: object) -> str:
    return _canonical_hash_domain("document_block_hash", payload)


def evidence_binding_hash(payload: object) -> str:
    return _canonical_hash_domain("evidence_binding_hash", payload)


def extraction_input_block_set_hash(block_ids: list[UUID] | tuple[UUID, ...]) -> str:
    if not block_ids:
        raise ValueError("ordered input block IDs must not be empty")
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("ordered input block IDs must be unique")
    return _canonical_hash_domain(
        "extraction_input_block_set_hash",
        {"ordered_input_block_ids": [str(block_id) for block_id in block_ids]},
    )


def extraction_evidence_binding_hash(
    bindings: list[tuple[UUID, str]] | tuple[tuple[UUID, str], ...],
) -> str:
    if not bindings:
        raise ValueError("extraction evidence bindings must not be empty")
    for _, binding_hash in bindings:
        if not _SHA256_PATTERN.fullmatch(binding_hash):
            raise ValueError("evidence binding hash must be lowercase SHA-256")
    return _canonical_hash_domain(
        "extraction_evidence_binding_hash",
        {
            "ordered_block_bindings": [
                {"block_id": str(block_id), "evidence_binding_hash": binding_hash}
                for block_id, binding_hash in bindings
            ]
        },
    )


def fact_dependency_fingerprint(payload: object) -> str:
    return _canonical_hash_domain("fact_dependency_fingerprint", payload)


def gold_truth_hash(payload: object) -> str:
    return _canonical_hash_domain("gold_truth_hash", payload)


def model_request_hash(payload: object) -> str:
    return _canonical_hash_domain("model_request_hash", payload)


__all__ = [
    "HASH_CONTRACT_VERSION",
    "HashDomain",
    "canonical_bundle_hash",
    "canonical_hash",
    "canonical_json_bytes",
    "document_parse_key",
    "document_block_hash",
    "evidence_binding_hash",
    "extraction_evidence_binding_hash",
    "extraction_input_block_set_hash",
    "fact_dependency_fingerprint",
    "gold_truth_hash",
    "member_provenance_hash",
    "model_request_hash",
    "split_manifest_hash",
]
