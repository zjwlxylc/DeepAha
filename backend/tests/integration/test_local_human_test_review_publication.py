from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid7

import pytest
from sqlalchemy import Engine, func, select

from deepaha.local_human_test.contracts import ItemStatus
from deepaha.local_human_test.models import (
    LocalHumanTestItem,
    LocalHumanTestReviewDecision,
)
from deepaha.local_human_test.publication import (
    LocalCatalogPublicationService,
    PublicationIdempotencyConflict,
)
from deepaha.local_human_test.review import (
    FactDecisionCommand,
    HumanFactReviewService,
    HumanReviewError,
    HumanRuleReviewService,
    ReviewIdempotencyConflict,
    RuleDecisionCommand,
)
from deepaha.p9b.models import (
    FactVerificationDecisionModel,
    RuleApprovalDecisionModel,
    VerifiedFact,
)
from deepaha.public_catalog.schemas import PublicOpportunityQuery
from deepaha.public_catalog.service import PublicCatalogService
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerPrincipal,
    ReviewerRole,
)
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration import test_local_human_test_extraction as extraction_support

human_extraction_engine = extraction_support.human_extraction_engine
pytestmark = pytest.mark.integration


def _human() -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=uuid7(),
        roles=frozenset({ReviewerRole.VALIDATION_REVIEWER}),
        purposes=frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}),
        synthetic=False,
    )


def test_human_fact_and_rule_review_is_independent_idempotent_and_audited(
    human_extraction_engine: Engine,
    tmp_path: Path,
) -> None:
    coordinator, adapter, factory, item_id = extraction_support._coordinator(
        human_extraction_engine,
        tmp_path,
        fact_field_name="education_requirements",
        fact_value={"minimum_level": "BACHELOR"},
    )
    extraction = coordinator.extract(item_id)
    assert extraction.status is ItemStatus.FACT_REVIEW
    assert len(adapter.invocations) == 1
    candidate_id = extraction.candidate_ids[0]
    principal = _human()
    with factory.begin() as session:
        session.add(
            ReviewerAccountModel(
                reviewer_id=principal.reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"human-validator-{principal.reviewer_id}",
                roles=[ReviewerRole.VALIDATION_REVIEWER.value],
                allowed_purposes=[OPPORTUNITY_FACT_VALIDATION_PURPOSE],
                created_at=datetime.now(UTC),
            )
        )
    facts = HumanFactReviewService(session_factory=factory)

    first = facts.decide(
        FactDecisionCommand(
            item_id=item_id,
            candidate_id=candidate_id,
            decision="APPROVE",
            reason="人工核对官方原文后确认。",
        ),
        principal,
        "fact-review-1",
    )
    repeated = facts.decide(
        FactDecisionCommand(
            item_id=item_id,
            candidate_id=candidate_id,
            decision="APPROVE",
            reason="人工核对官方原文后确认。",
        ),
        principal,
        "fact-review-1",
    )
    assert repeated == first

    with pytest.raises(ReviewIdempotencyConflict):
        facts.decide(
            FactDecisionCommand(
                item_id=item_id,
                candidate_id=candidate_id,
                decision="REJECT",
                reason="同一键不能改变决定。",
            ),
            principal,
            "fact-review-1",
        )

    promoted = facts.promote(item_id, principal)
    assert promoted.promoted_field_names == ("education_requirements",)
    assert facts.promote(item_id, principal) == promoted

    rules = HumanRuleReviewService(session_factory=factory)
    proposal = rules.propose_from_verified_facts(item_id)
    assert len(proposal.candidates) == 1
    assert proposal.eligibility_ceiling == "UNCERTAIN"
    rule_candidate = proposal.candidates[0]
    assert rule_candidate.verified_fact_ids
    assert rule_candidate.evidence_ref_ids

    approved = rules.decide(
        RuleDecisionCommand(
            item_id=item_id,
            rule_candidate_id=rule_candidate.rule_candidate_id,
            decision="APPROVE",
            reason="人工确认该资格条件可执行。",
        ),
        principal,
        "rule-review-1",
    )
    repeated_approval = rules.decide(
        RuleDecisionCommand(
            item_id=item_id,
            rule_candidate_id=rule_candidate.rule_candidate_id,
            decision="APPROVE",
            reason="人工确认该资格条件可执行。",
        ),
        principal,
        "rule-review-1",
    )
    assert repeated_approval == approved
    assert approved.eligibility_ceiling == "RULE_EVALUATED"
    assert rules.propose_from_verified_facts(item_id).candidates == proposal.candidates

    with factory() as session:
        item = session.get(LocalHumanTestItem, item_id)
        fact_decision = session.get(FactVerificationDecisionModel, first.decision_id)
        rule_decision = session.get(
            RuleApprovalDecisionModel,
            approved.decision_id,
        )
        assert item is not None and item.status == ItemStatus.READY_TO_PUBLISH.value
        assert fact_decision is not None
        assert fact_decision.verifier_identity == f"human:{principal.reviewer_id}"
        assert fact_decision.verifier_identity != "component:local-human-extractor/1.0.0"
        assert rule_decision is not None
        assert rule_decision.approver_identity == f"human:{principal.reviewer_id}"
        assert (
            session.scalar(
                select(func.count())
                .select_from(VerifiedFact)
                .where(VerifiedFact.verified_fact_set_id == item.verified_fact_set_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(LocalHumanTestReviewDecision)
                .where(LocalHumanTestReviewDecision.item_id == item_id)
            )
            == 2
        )


def test_only_complete_human_verified_official_facts_publish_to_local_catalog(
    human_extraction_engine: Engine,
    tmp_path: Path,
) -> None:
    fact_values: tuple[tuple[str, object], ...] = (
        ("canonical_title", "浙江省青年科研计划申报公告"),
        ("type", "RESEARCH_PROGRAM"),
        ("issuer_name", "浙江省示例主管部门"),
        ("jurisdiction", "浙江省"),
        ("status", "CLOSING_SOON"),
        ("published_at", "2026-08-20T08:00:00+08:00"),
        (
            "application_window",
            {
                "opens_on": "2026-08-20",
                "closes_on": "2026-09-20",
                "timezone": "Asia/Shanghai",
            },
        ),
        ("application_url", "https://official.example.gov.cn/apply"),
        (
            "attachment_urls",
            ["https://official.example.gov.cn/notice/attachment.pdf"],
        ),
        ("locations", ["浙江省"]),
    )
    coordinator, _adapter, factory, item_id = extraction_support._coordinator(
        human_extraction_engine,
        tmp_path,
        facts=fact_values,
    )
    extraction = coordinator.extract(item_id)
    assert extraction.status is ItemStatus.FACT_REVIEW
    principal = _human()
    with factory.begin() as session:
        session.add(
            ReviewerAccountModel(
                reviewer_id=principal.reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"human-publisher-{principal.reviewer_id}",
                roles=[ReviewerRole.VALIDATION_REVIEWER.value],
                allowed_purposes=[OPPORTUNITY_FACT_VALIDATION_PURPOSE],
                created_at=datetime.now(UTC),
            )
        )

    facts = HumanFactReviewService(session_factory=factory)
    for index, candidate_id in enumerate(extraction.candidate_ids, start=1):
        facts.decide(
            FactDecisionCommand(
                item_id=item_id,
                candidate_id=candidate_id,
                decision="APPROVE",
                reason="人工逐项核对官方原文。",
            ),
            principal,
            f"publication-fact-{index}",
        )
    facts.promote(item_id, principal)
    proposal = HumanRuleReviewService(session_factory=factory).propose_from_verified_facts(item_id)
    assert proposal.candidates == ()
    assert proposal.eligibility_ceiling == "UNCERTAIN"

    publications = LocalCatalogPublicationService(session_factory=factory)
    blocked_preview = publications.preview(item_id)
    assert not blocked_preview.eligible
    assert "PUBLICATION_CONTENT_USE_NOT_APPROVED" in blocked_preview.blocker_codes
    assert "PUBLICATION_URL_OUTSIDE_ALLOWED_HOSTS" in blocked_preview.blocker_codes

    with factory.begin() as session:
        item = session.get(LocalHumanTestItem, item_id)
        assert item is not None and item.endpoint_id is not None
        endpoint = session.get(SourceEndpoint, item.endpoint_id)
        assert endpoint is not None
        endpoint.content_use_basis = "OFFICIAL_PUBLIC_ACCESS"
        endpoint.allowed_hosts = sorted({*endpoint.allowed_hosts, "official.example.gov.cn"})
    preview = publications.preview(item_id)
    assert preview.eligible
    assert preview.missing_field_names == ()
    assert preview.official_evidence_complete
    assert preview.content_use_basis == "OFFICIAL_PUBLIC_ACCESS"

    with pytest.raises(HumanReviewError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        publications.publish(
            item_id,
            ReviewerPrincipal(
                reviewer_id=uuid7(),
                roles=frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
                purposes=frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}),
                synthetic=False,
            ),
            "unauthorized-publication",
        )

    first = publications.publish(item_id, principal, "publication-1")
    repeated = publications.publish(item_id, principal, "publication-1")
    assert first.repeated is False
    assert repeated.repeated is True
    assert repeated.decision_id == first.decision_id
    assert repeated.opportunity_version == first.opportunity_version
    with pytest.raises(PublicationIdempotencyConflict):
        publications.publish(item_id, _human(), "publication-1")

    with factory() as session:
        item = session.get(LocalHumanTestItem, item_id)
        page = PublicCatalogService(session).list_opportunities(PublicOpportunityQuery())
        assert item is not None and item.status == ItemStatus.COMPLETED.value
        published = next(
            value for value in page.items if value.title == "浙江省青年科研计划申报公告"
        )
        assert published.data_label.value == "LOCAL_HUMAN_REVIEWED"
        assert published.issuer_name == "浙江省示例主管部门"
