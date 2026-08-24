from uuid import UUID

import pytest

from deepaha.p9b.hashing import (
    HASH_CONTRACT_VERSION,
    HashDomain,
    canonical_bundle_hash,
    canonical_json_bytes,
    document_parse_key,
    member_provenance_hash,
    split_manifest_hash,
)


def test_canonical_json_has_frozen_field_order_null_unicode_and_array_order() -> None:
    payload = {"c": [2, 1], "b": "机会", "a": None}

    assert canonical_json_bytes(payload) == '{"a":null,"b":"机会","c":[2,1]}'.encode()
    assert HASH_CONTRACT_VERSION == "p9b-canonical-json-sha256-v1"
    assert canonical_bundle_hash(payload) == (
        "89ee0f9337fd71b42610d8763a72488242c9aac800044e005b47e75c481c5480"
    )


def test_document_parse_key_matches_frozen_domain_separated_vector() -> None:
    assert (
        document_parse_key(
            artifact_id=UUID("019c0000-0000-7000-8000-000000000111"),
            artifact_sha256="a" * 64,
            parser_name="deepaha-html",
            parser_version="1.0.0",
            parse_contract_version="phase2-locator-contract-v0.2.0",
        )
        == "76a7a2cd02753d93e0d459a02ff26e73f0d775ad97c28c781ead845b7dd0125d"
    )


def test_bundle_and_split_domains_cannot_collide_for_same_payload() -> None:
    payload = {"entries": [], "expected_entry_count": 30, "partition": "CALIBRATION"}

    assert split_manifest_hash(payload) == (
        "53a760c94fcaf2d591d2c990e338f9dde15274170252bcf8bde97cd32cf103c8"
    )
    assert split_manifest_hash(payload) != canonical_bundle_hash(payload)
    assert {domain.value for domain in HashDomain} == {
        "document_parse_key",
        "canonical_bundle_hash",
        "split_manifest_hash",
        "member_provenance_hash",
    }


def test_member_provenance_hash_has_its_own_frozen_domain() -> None:
    payload = {
        "source_bundle_revision_id": "019c0000-0000-7000-8000-000000000101",
        "source_bundle_member_id": "019c0000-0000-7000-8000-000000000102",
        "raw_artifact_sha256": "b" * 64,
        "document_parse_key": "c" * 64,
        "member_role": "ATTACHMENT",
        "precedence": 200,
    }

    assert member_provenance_hash(payload) == (
        "903ee93166559012b66120069324a183a98f9e20716a9c56d25f34a581d3ee9c"
    )
    assert member_provenance_hash(payload) != canonical_bundle_hash(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_json_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="JSON"):
        canonical_json_bytes({"value": value})


def test_canonical_json_rejects_implicit_uuid_stringification() -> None:
    with pytest.raises(TypeError):
        canonical_json_bytes({"id": UUID("019c0000-0000-7000-8000-000000000111")})
