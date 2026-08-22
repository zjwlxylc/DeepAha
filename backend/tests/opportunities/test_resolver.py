import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import (
    ApplicationWindowSchema,
    OpportunityDocumentRole,
    ResolutionDisposition,
)
from deepaha.opportunities.identity import (
    normalize_identity_text,
    normalize_official_url,
    stable_public_id_for_key,
    weak_fingerprint,
)
from deepaha.opportunities.resolver import resolve_document
from deepaha.opportunities.types import (
    OpportunityPatch,
    ResolutionDecision,
    ResolutionDocument,
    ResolutionIndex,
    ResolutionTarget,
)

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "opportunities" / "phase3-resolution-cases.json"
)
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")
OTHER_SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000002")
DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000000010")
EVIDENCE_REF_ID = UUID("019b0000-0000-7000-8000-000000000011")
TARGET_ID = UUID("019b0000-0000-7000-8000-000000000020")
OTHER_TARGET_ID = UUID("019b0000-0000-7000-8000-000000000021")
PRIMARY_KEY = "external:019b0000-0000-7000-8000-000000000001:deepaha-2026-001"
PUBLIC_ID = "opp_63be197cc6ef3632650c5f69b5938f0b"
FIXTURE_CONTENT_SHA256 = "1ab32974f7dc982bb6cf12b8d023a53b136136b1c254779003b789734d8f7f82"


def test_resolution_fixture_bytes_are_fixed() -> None:
    assert sha256(FIXTURE_PATH.read_bytes()).hexdigest() == FIXTURE_CONTENT_SHA256


def patch_values(**changes: object) -> OpportunityPatch:
    values: dict[str, object] = {
        "canonical_title": "Synthetic youth opportunity",
        "type": OpportunityTypeV02.YOUTH_DEVELOPMENT_PROGRAM,
        "issuer_name": "Synthetic Example Authority",
        "jurisdiction": "Synthetic Region",
        "status": OpportunityStatus.OPEN,
        "published_at": NOW,
        "application_url": "https://example.gov/apply",
        "attachment_urls": (),
        "locations": (),
    }
    values.update(changes)
    return OpportunityPatch(**values)  # type: ignore[arg-type]


def primary_document(**changes: object) -> ResolutionDocument:
    values: dict[str, object] = {
        "document_id": DOCUMENT_ID,
        "source_id": SOURCE_ID,
        "source_tier": SourceTier.OFFICIAL_PRIMARY,
        "evidence_ref_id": EVIDENCE_REF_ID,
        "role": OpportunityDocumentRole.PRIMARY_NOTICE,
        "canonical_url": "https://example.gov/notices/1",
        "external_id": "DeepAha-2026-001",
        "references_document_ids": (),
        "effective_at": NOW,
        "facts": patch_values(),
    }
    values.update(changes)
    return ResolutionDocument(**values)  # type: ignore[arg-type]


def target(
    opportunity_id: UUID = TARGET_ID,
    public_id: str = PUBLIC_ID,
    primary_identity_key: str = PRIMARY_KEY,
) -> ResolutionTarget:
    return ResolutionTarget(
        opportunity_id=opportunity_id,
        public_id=public_id,
        primary_identity_key=primary_identity_key,
    )


def test_primary_official_document_creates_literal_stable_public_id() -> None:
    decision = resolve_document(primary_document(), ResolutionIndex.empty())

    assert decision.disposition is ResolutionDisposition.CREATED
    assert decision.opportunity_id is None
    assert decision.public_id == PUBLIC_ID
    assert decision.resolution_key == PRIMARY_KEY


def test_stable_public_id_uses_literal_domain_separator() -> None:
    assert stable_public_id_for_key(PRIMARY_KEY) == PUBLIC_ID


def test_url_normalization_preserves_query_and_removes_only_safe_components() -> None:
    assert (
        normalize_official_url("HTTPS://Example.GOV:443?batch=01%2F02#section")
        == "https://example.gov/?batch=01%2F02"
    )
    assert normalize_official_url("http://Example.GOV:80/notices") == ("http://example.gov/notices")


@pytest.mark.parametrize(
    "url",
    ["/relative", "ftp://example.gov/a", "https://user:secret@example.gov/a"],
)
def test_url_normalization_rejects_nonofficial_shapes(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_official_url(url)


def test_external_id_normalization_is_unicode_and_source_scoped() -> None:
    assert normalize_identity_text("  DEEPAHA\u3000A\u0301  ") == "deepaha á"
    document = primary_document(
        source_id=OTHER_SOURCE_ID,
        canonical_url=None,
        external_id="DeepAha-2026-001",
    )
    index = ResolutionIndex(external_keys={PRIMARY_KEY: (target(),)})

    decision = resolve_document(document, index)

    assert decision.disposition is ResolutionDisposition.CREATED
    assert decision.resolution_key.startswith(f"external:{OTHER_SOURCE_ID}:")


def test_same_title_without_shared_strong_key_never_hard_merges() -> None:
    fingerprint = weak_fingerprint(patch_values())
    assert fingerprint is not None
    document = primary_document(external_id="DEEPAHA-2026-OTHER", canonical_url=None)
    index = ResolutionIndex(weak_candidates={fingerprint: (target(),)})

    decision = resolve_document(document, index)

    assert decision.disposition is ResolutionDisposition.NEEDS_REVIEW
    assert decision.candidate_opportunity_ids == (TARGET_ID,)
    assert decision.reason_codes == ("POSSIBLE_DUPLICATE",)


def test_conflicting_strong_keys_never_choose_by_input_order() -> None:
    first_target = target()
    second_target = target(
        opportunity_id=OTHER_TARGET_ID,
        public_id="opp_019b0000000070008000000000000021",
        primary_identity_key="external:other",
    )
    first_reference = UUID("019b0000-0000-7000-8000-000000000030")
    second_reference = UUID("019b0000-0000-7000-8000-000000000031")
    index = ResolutionIndex(
        document_links={first_reference: first_target, second_reference: second_target}
    )
    document = primary_document(
        external_id=None,
        canonical_url=None,
        references_document_ids=(first_reference, second_reference),
    )

    first = resolve_document(document, index)
    second = resolve_document(
        replace(
            document, references_document_ids=tuple(reversed(document.references_document_ids))
        ),
        index,
    )

    assert first == second
    assert first.disposition is ResolutionDisposition.NEEDS_REVIEW
    assert first.candidate_opportunity_ids == (TARGET_ID, OTHER_TARGET_ID)
    assert first.reason_codes == ("STRONG_KEY_CONFLICT",)


def test_missing_stable_key_and_incomplete_primary_facts_need_review() -> None:
    no_key = resolve_document(
        primary_document(external_id=None, canonical_url=None),
        ResolutionIndex.empty(),
    )
    incomplete = resolve_document(
        primary_document(
            facts=patch_values(canonical_title=""),
        ),
        ResolutionIndex.empty(),
    )

    assert no_key.reason_codes == ("MISSING_STABLE_KEY",)
    assert incomplete.reason_codes == ("INCOMPLETE_PRIMARY_FACTS",)


@pytest.mark.parametrize(
    "role",
    [
        OpportunityDocumentRole.ATTACHMENT,
        OpportunityDocumentRole.POSITION_TABLE,
        OpportunityDocumentRole.CORRECTION,
        OpportunityDocumentRole.DEADLINE_EXTENSION,
        OpportunityDocumentRole.CANCELLATION,
        OpportunityDocumentRole.RESULT,
    ],
)
def test_nonprimary_document_without_strong_relation_needs_review(
    role: OpportunityDocumentRole,
) -> None:
    decision = resolve_document(
        primary_document(
            role=role,
            external_id=None,
            canonical_url=None,
            references_document_ids=(),
        ),
        ResolutionIndex.empty(),
    )

    assert decision.reason_codes == ("MISSING_STRONG_RELATION",)


@pytest.mark.parametrize(
    ("tier", "reason"),
    [
        (SourceTier.OFFICIAL_AGGREGATOR, "AGGREGATOR_REQUIRES_REVIEW"),
        (SourceTier.TRUSTED_SECONDARY, "UNTRUSTED_SOURCE_TIER"),
        (SourceTier.COMMUNITY_SIGNAL, "UNTRUSTED_SOURCE_TIER"),
    ],
)
def test_nonprimary_source_never_hard_links(tier: SourceTier, reason: str) -> None:
    index = ResolutionIndex(external_keys={PRIMARY_KEY: (target(),)})

    decision = resolve_document(primary_document(source_tier=tier), index)

    assert decision.disposition is ResolutionDisposition.NEEDS_REVIEW
    assert decision.candidate_opportunity_ids == (TARGET_ID,)
    assert decision.reason_codes == (reason,)


def test_primary_strong_key_links_existing_opportunity() -> None:
    index = ResolutionIndex(external_keys={PRIMARY_KEY: (target(),)})

    decision = resolve_document(primary_document(), index)

    assert decision.disposition is ResolutionDisposition.LINKED
    assert decision.opportunity_id == TARGET_ID
    assert decision.public_id == PUBLIC_ID
    assert decision.resolution_key == PRIMARY_KEY


def test_duplicate_document_replay_returns_prior_decision() -> None:
    prior = ResolutionDecision(
        disposition=ResolutionDisposition.NEEDS_REVIEW,
        opportunity_id=None,
        public_id=None,
        candidate_opportunity_ids=(TARGET_ID,),
        reason_codes=("PRIOR_REVIEW",),
        resolution_key=f"document:{DOCUMENT_ID}",
    )
    index = ResolutionIndex(decisions_by_document={DOCUMENT_ID: prior})

    assert resolve_document(primary_document(), index) is prior


def test_resolution_index_sorts_candidates_and_is_immutable() -> None:
    fingerprint = weak_fingerprint(patch_values())
    assert fingerprint is not None
    raw = {
        fingerprint: (
            target(opportunity_id=OTHER_TARGET_ID),
            target(opportunity_id=TARGET_ID),
        )
    }
    index = ResolutionIndex(weak_candidates=raw)
    raw.clear()

    assert tuple(item.opportunity_id for item in index.weak_candidates[fingerprint]) == (
        TARGET_ID,
        OTHER_TARGET_ID,
    )
    with pytest.raises(TypeError):
        index.weak_candidates[fingerprint] = ()  # type: ignore[index]


def document_from_case(case: dict[str, object]) -> ResolutionDocument:
    raw_facts = case["facts"]
    assert isinstance(raw_facts, dict)
    facts: dict[str, object] = dict(raw_facts)
    if "type" in facts:
        facts["type"] = OpportunityTypeV02(str(facts["type"]))
    if "status" in facts:
        facts["status"] = OpportunityStatus(str(facts["status"]))
    if "application_window" in facts:
        facts["application_window"] = ApplicationWindowSchema.model_validate(
            facts["application_window"]
        )
    for name in ("attachment_urls", "locations"):
        if name in facts:
            value = facts[name]
            assert isinstance(value, list)
            facts[name] = tuple(str(item) for item in value)
    references = case["references_document_ids"]
    assert isinstance(references, list)
    return ResolutionDocument(
        document_id=UUID(str(case["document_id"])),
        source_id=UUID(str(case["source_id"])),
        source_tier=SourceTier(str(case["source_tier"])),
        evidence_ref_id=UUID(str(case["evidence_ref_id"])),
        role=OpportunityDocumentRole(str(case["role"])),
        canonical_url=None if case["canonical_url"] is None else str(case["canonical_url"]),
        external_id=None if case["external_id"] is None else str(case["external_id"]),
        references_document_ids=tuple(UUID(str(item)) for item in references),
        effective_at=datetime.fromisoformat(str(case["effective_at"])),
        facts=OpportunityPatch(**facts),  # type: ignore[arg-type]
    )


def index_for_case(case_id: str, document: ResolutionDocument) -> ResolutionIndex:
    if case_id == "primary":
        return ResolutionIndex.empty()
    if case_id == "duplicate":
        return ResolutionIndex(external_keys={PRIMARY_KEY: (target(),)})
    if case_id in {
        "attachment",
        "position_table",
        "correction",
        "deadline_extension",
        "cancellation",
    }:
        return ResolutionIndex(document_links={DOCUMENT_ID: target()})
    if case_id == "lower_priority_conflict":
        other_key = f"external:{OTHER_SOURCE_ID}:other-001"
        return ResolutionIndex(
            document_links={DOCUMENT_ID: target()},
            external_keys={
                other_key: (
                    target(
                        opportunity_id=OTHER_TARGET_ID,
                        public_id="opp_019b0000000070008000000000000021",
                        primary_identity_key=other_key,
                    ),
                )
            },
        )
    assert case_id == "possible_false_merge"
    fingerprint = weak_fingerprint(document.facts)
    assert fingerprint is not None
    return ResolutionIndex(weak_candidates={fingerprint: (target(),)})


def test_fixed_synthetic_fixture_executes_expected_resolution_matrix() -> None:
    fixture: dict[str, object] = json.loads(FIXTURE_PATH.read_text("utf-8"))
    assert fixture["schema_version"] == "0.3.0"
    assert fixture["synthetic"] is True
    assert fixture["contains_business_facts"] is False
    assert fixture["license"] == "CC0-1.0 synthetic fixture"
    cases = fixture["cases"]
    assert isinstance(cases, list)
    assert [(case["case_id"], case["expected"]) for case in cases] == [
        ("primary", "CREATED"),
        ("duplicate", "LINKED"),
        ("attachment", "LINKED"),
        ("position_table", "LINKED"),
        ("correction", "LINKED"),
        ("deadline_extension", "LINKED"),
        ("cancellation", "LINKED"),
        ("lower_priority_conflict", "NEEDS_REVIEW"),
        ("possible_false_merge", "NEEDS_REVIEW"),
    ]
    for case in cases:
        assert isinstance(case, dict)
        document = document_from_case(case)
        decision = resolve_document(document, index_for_case(str(case["case_id"]), document))
        assert decision.disposition.value == case["expected"]


def test_pure_resolver_modules_have_no_persistence_or_network_imports() -> None:
    root = Path(__file__).parents[2] / "src" / "deepaha" / "opportunities"
    source = "\n".join(
        (root / filename).read_text("utf-8")
        for filename in ("types.py", "identity.py", "resolver.py")
    )
    for forbidden in ("sqlalchemy", "httpx", "boto", "redis", "playwright", "openai"):
        assert forbidden not in source.lower()
