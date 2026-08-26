from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

from deepaha.local_human_test.publication import (
    LocalPublicationError,
    PublicationFact,
    build_publication_material,
)

EVIDENCE_ID = UUID("019d0000-0000-7000-8000-000000000201")
EFFECTIVE_AT = datetime(2026, 8, 26, tzinfo=UTC)


def _facts() -> tuple[PublicationFact, ...]:
    values: dict[str, JsonValue] = {
        "canonical_title": "浙江省青年科研计划申报公告",
        "type": "RESEARCH_PROGRAM",
        "issuer_name": "浙江省示例主管部门",
        "jurisdiction": "浙江省",
        "status": "OPEN",
        "published_at": "2026-08-20T08:00:00+08:00",
        "application_window": {
            "opens_on": "2026-08-20",
            "closes_on": "2026-09-20",
            "timezone": "Asia/Shanghai",
        },
        "application_url": "https://official.example.gov.cn/apply",
        "attachment_urls": ["https://official.example.gov.cn/notice/attachment.pdf"],
        "locations": ["浙江省"],
    }
    return tuple(
        PublicationFact(
            field_name=field_name,
            normalized_value=value,
            evidence_ref_id=EVIDENCE_ID,
            effective_at=EFFECTIVE_AT,
        )
        for field_name, value in values.items()
    )


def test_build_publication_material_requires_complete_verified_public_facts() -> None:
    material = build_publication_material(_facts())

    assert material.snapshot.canonical_title == "浙江省青年科研计划申报公告"
    assert material.snapshot.type.value == "RESEARCH_PROGRAM"
    assert material.snapshot.status.value == "OPEN"
    assert material.snapshot.application_window.closes_on is not None
    assert material.snapshot.application_window.closes_on.isoformat() == "2026-09-20"
    assert {item.field_path.value for item in material.field_evidence} == {
        "canonical_title",
        "type",
        "issuer_name",
        "jurisdiction",
        "status",
        "published_at",
        "application_window.opens_on",
        "application_window.closes_on",
        "application_window.timezone",
        "application_url",
        "attachment_urls",
        "locations",
    }
    assert len(material.content_sha256) == 64


def test_missing_or_duplicate_public_fact_fails_closed() -> None:
    facts = _facts()
    with pytest.raises(LocalPublicationError, match="PUBLICATION_FACTS_INCOMPLETE"):
        build_publication_material(facts[:-1])

    with pytest.raises(LocalPublicationError, match="DUPLICATE_PUBLICATION_FACT"):
        build_publication_material((*facts, facts[0]))


def test_invalid_normalized_value_fails_closed() -> None:
    facts = tuple(
        PublicationFact(
            field_name=fact.field_name,
            normalized_value=(
                "javascript:alert(1)"
                if fact.field_name == "application_url"
                else fact.normalized_value
            ),
            evidence_ref_id=fact.evidence_ref_id,
            effective_at=fact.effective_at,
        )
        for fact in _facts()
    )

    with pytest.raises(LocalPublicationError, match="PUBLICATION_FACT_VALUE_INVALID"):
        build_publication_material(facts)
