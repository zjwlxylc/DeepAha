from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.contracts.phase9b import (
    EvidenceSupportResult,
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    ExtractionRunStatus,
    ExtractionTargetScope,
    ExtractorKind,
    FactVerificationDecision,
    FactVerificationDecisionSchemaV08,
    PrecedenceCheckResult,
    ProposedRulePayloadSchemaV08,
    RuleApprovalDecisionSchemaV08,
    RuleApprovalDecisionValue,
    RuleApprovalMethod,
    RuleCandidateSchemaV08,
    RuleCandidateStatus,
    VerificationMethod,
)
from deepaha.core.settings import Settings
from deepaha.documents.html import P9BHtmlDocumentParser
from deepaha.documents.models import DocumentBlock
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.facts import FactLifecycleService, extraction_input_block_set_hash
from deepaha.p9b.hashing import extraction_evidence_binding_hash
from deepaha.p9b.identity import OpportunityUnitService, UnitSeed
from deepaha.p9b.models import (
    FactVerificationDecisionModel,
    SourceBundleRevision,
    UnitRuleSet,
    VerifiedFact,
    VerifiedFactSetDependency,
    VerifiedFactSetTransition,
    VersionedVerifiedFactSet,
)
from deepaha.p9b.provenance import BundleMemberSpec, BundleService
from deepaha.p9b.rules import RulePromotionService
from deepaha.rules.models import RuleSetModel
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
CONTENT = b"<html lang='zh-CN'><body><main><p>Education: BACHELOR</p></main></body></html>"
CONTENT_HASH = sha256(CONTENT).hexdigest()


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass(frozen=True, slots=True)
class FactGraph:
    opportunity_id: UUID
    opportunity_version: int
    opportunity_unit_id: UUID
    opportunity_unit_version_id: UUID
    source_bundle_revision_id: UUID
    block_id: UUID
    evidence_ref_id: UUID
    evidence_binding_hash: str


def seed_fact_graph(engine: Engine, object_store: S3ObjectStore) -> FactGraph:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    source_id = uuid7()
    endpoint_id = uuid7()
    observation_id = uuid7()
    evaluation_id = uuid7()
    acquisition_run_id = uuid7()
    recipe_id = uuid7()
    url = f"https://p9b-facts-{source_id.hex}.example.gov/notices/1"
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id=f"src_{source_id.hex}",
                canonical_url=f"https://p9b-facts-{source_id.hex}.example.gov/",
                authority_name="Synthetic P9-B fact authority",
                tier="OFFICIAL_PRIMARY",
                jurisdiction=None,
                active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            SourceEndpoint(
                endpoint_id=endpoint_id,
                source_id=source_id,
                url=url,
                allowed_hosts=[f"p9b-facts-{source_id.hex}.example.gov"],
                expected_media_types=["text/html"],
                browser_policy="NEVER",
                minimum_interval_seconds=21_600,
                timeout_seconds=30,
                max_attempts=2,
                robots_url=f"https://p9b-facts-{source_id.hex}.example.gov/robots.txt",
                robots_decision="ALLOWED",
                robots_checked_at=NOW,
                content_use_basis="LINK_ONLY",
                license_name=None,
                license_url=None,
                attribution="Synthetic P9-B fact authority",
                fixture_storage_allowed=False,
                usage_note="Synthetic fact lifecycle persistence test only.",
                policy_version="2026-08-24.1",
                active=True,
                verified_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        imported = import_raw_artifact(
            session=session,
            object_store=object_store,
            command=ImportRawArtifactCommand(
                source_id=source_id,
                requested_url=url,
                resolved_url=url,
                retrieved_at=NOW,
                http_status=200,
                media_type="text/html",
                content=CONTENT,
                collector_version="test/0.8.0",
                metadata_schema_version="0.2.0",
            ),
        )
        artifact_id = imported.artifact.artifact_id
        session.add_all(
            [
                CaptureObservation(
                    observation_id=observation_id,
                    collection_run_id=uuid7(),
                    attempt_number=1,
                    endpoint_id=endpoint_id,
                    source_id=source_id,
                    requested_url=url,
                    resolved_url=url,
                    started_at=NOW,
                    completed_at=NOW,
                    outcome="SUCCEEDED",
                    http_status=200,
                    response_etag=None,
                    response_last_modified=None,
                    artifact_id=artifact_id,
                    error_code=None,
                    collector_name="static-http",
                    collector_version="test/0.8.0",
                    policy_version="2026-08-24.1",
                ),
                AcquisitionRun(
                    acquisition_run_id=acquisition_run_id,
                    recipe_id=recipe_id,
                    source_id=source_id,
                    endpoint_id=endpoint_id,
                    endpoint_policy_version="2026-08-24.1",
                    recipe_version="2026-08-24.1",
                    started_at=NOW,
                    completed_at=NOW,
                    terminal_code="COMPLETE",
                    request_count=1,
                    strategy_attempts=[{"strategy": "STATIC_HTTP", "outcome": "VALID"}],
                    discovered_count=1,
                    validated_count=1,
                    parsed_count=1,
                    attachment_count=0,
                    evidence_count=1,
                    zero_discovery_flag=False,
                    selector_drift_flag=False,
                    manual_intervention=False,
                    stable_stop_reason=None,
                    contract_version="1.0.0",
                ),
            ]
        )
        session.flush()
        session.add(
            AcquisitionEvaluation(
                acquisition_evaluation_id=evaluation_id,
                observation_id=observation_id,
                endpoint_id=endpoint_id,
                source_id=source_id,
                artifact_id=artifact_id,
                strategy_used="STATIC_HTTP",
                validation_status="VALID",
                challenge_type=None,
                redirect_chain=[url],
                discovered_count=1,
                manual_intervention=False,
                diagnostic_codes=[],
                validator_name="deepaha-content-validator",
                validator_version="1.0.0",
                metrics_schema_version="1.0.0",
                validation_metrics={"byte_size": len(CONTENT)},
                evaluated_at=NOW,
                contract_version="1.0.0",
            )
        )

    parsed = DocumentService(
        session_factory=factory,
        object_store=object_store,
        parsers=[P9BHtmlDocumentParser()],
        clock=FixedClock(),
    ).parse(ParseDocumentCommand(artifact_id=artifact_id))
    assert parsed.document_id is not None
    assert len(parsed.document_block_ids) == 1

    with factory.begin() as session:
        block = session.get(DocumentBlock, parsed.document_block_ids[0])
        assert block is not None
        opportunity_id = uuid7()
        opportunity = Opportunity(
            opportunity_id=opportunity_id,
            public_id=f"opp_{opportunity_id.hex}",
            type="YOUTH_DEVELOPMENT_PROGRAM",
            canonical_title="Synthetic fact opportunity",
            issuer_name="Synthetic P9-B fact authority",
            jurisdiction=None,
            current_version=None,
            status="OPEN",
            publication_status="INTERNAL",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(opportunity)
        session.flush()
        session.add(
            OpportunityVersion(
                opportunity_id=opportunity_id,
                version=1,
                effective_from=NOW,
                source_document_id=parsed.document_id,
                source_evidence_ref_id=block.evidence_ref_id,
                snapshot={
                    "canonical_title": opportunity.canonical_title,
                    "type": opportunity.type,
                    "issuer_name": opportunity.issuer_name,
                    "jurisdiction": None,
                    "status": opportunity.status,
                    "published_at": NOW.isoformat(),
                    "application_window": {
                        "opens_on": None,
                        "closes_on": None,
                        "timezone": None,
                    },
                    "application_url": None,
                    "attachment_urls": [],
                    "locations": [],
                },
                field_evidence=[
                    {
                        "field_path": "canonical_title",
                        "precedence": 600,
                        "evidence_ref_id": str(block.evidence_ref_id),
                        "effective_at": NOW.isoformat(),
                    }
                ],
                changes=[
                    {
                        "field_path": "canonical_title",
                        "before": None,
                        "after": opportunity.canonical_title,
                        "evidence_ref_id": str(block.evidence_ref_id),
                    }
                ],
                content_sha256=CONTENT_HASH,
                review_status="NOT_REQUIRED",
                created_at=NOW,
            )
        )
        session.flush()
        opportunity.current_version = 1
        revision = BundleService(session).create_revision(
            opportunity_id=opportunity_id,
            opportunity_version=1,
            effective_as_of=NOW,
            members=[
                BundleMemberSpec(
                    document_id=parsed.document_id,
                    capture_observation_id=observation_id,
                    acquisition_evaluation_id=evaluation_id,
                    acquisition_run_id=acquisition_run_id,
                    member_role="PRIMARY_NOTICE",
                    precedence=1000,
                    effective_from=NOW,
                    effective_to=None,
                )
            ],
        )
        revision = BundleService(session).freeze_revision(
            revision.source_bundle_revision_id, frozen_at=NOW
        )
        unit = OpportunityUnitService(session).create_unit(
            opportunity_id=opportunity_id,
            opportunity_version=1,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            seed=UnitSeed("POSITION-001", "POSITION", "Position 001", "a" * 64),
            effective_from=NOW,
        )
        assert unit.current_version_id is not None
        return FactGraph(
            opportunity_id=opportunity_id,
            opportunity_version=1,
            opportunity_unit_id=unit.opportunity_unit_id,
            opportunity_unit_version_id=unit.current_version_id,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            block_id=block.block_id,
            evidence_ref_id=block.evidence_ref_id,
            evidence_binding_hash=block.evidence_binding_hash,
        )


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


def test_fact_promotion_and_dormant_unit_rule_chain_is_audited(
    migrated_engine: Engine, object_store: S3ObjectStore
) -> None:
    graph = seed_fact_graph(migrated_engine, object_store)
    run_id = uuid7()
    candidate_id = uuid7()
    decision_id = uuid7()
    fact_set_id = uuid7()
    block_ids = [graph.block_id]
    with Session(migrated_engine) as session:
        lifecycle = FactLifecycleService(session)
        lifecycle.persist_run(
            ExtractionRunSchemaV08(
                extraction_run_id=run_id,
                source_bundle_revision_id=graph.source_bundle_revision_id,
                target_scope=ExtractionTargetScope.UNIT,
                opportunity_id=graph.opportunity_id,
                opportunity_version=graph.opportunity_version,
                opportunity_unit_id=graph.opportunity_unit_id,
                opportunity_unit_version_id=graph.opportunity_unit_version_id,
                unit_segmentation_version="unit-segmentation/0.8.0",
                task_spec_version="p9b-extraction-task/0.8.0",
                extractor_kind=ExtractorKind.DETERMINISTIC,
                component_version="deterministic-fields/0.8.0",
                producer_identity="component:deterministic-fields/0.8.0",
                producer_response_id=None,
                ordered_input_block_ids=block_ids,
                input_block_set_hash=extraction_input_block_set_hash(block_ids),
                evidence_binding_hash=extraction_evidence_binding_hash(
                    [(graph.block_id, graph.evidence_binding_hash)]
                ),
                started_at=NOW,
                completed_at=NOW,
                status=ExtractionRunStatus.SUCCEEDED,
            )
        )
        lifecycle.record_candidate(
            ExtractionCandidateSchemaV08(
                candidate_id=candidate_id,
                extraction_run_id=run_id,
                target_scope=ExtractionTargetScope.UNIT,
                opportunity_id=graph.opportunity_id,
                opportunity_version=1,
                opportunity_unit_id=graph.opportunity_unit_id,
                opportunity_unit_version_id=graph.opportunity_unit_version_id,
                field_name="education_level",
                raw_value="BACHELOR",
                normalized_value_candidate="BACHELOR",
                evidence_block_ids=block_ids,
                evidence_ref_ids=[graph.evidence_ref_id],
                confidence=1.0,
                abstained=False,
                candidate_reason_code="DETERMINISTIC_ENUM",
                schema_version="0.8.0",
                created_at=NOW,
            )
        )
        lifecycle.verify_candidate(
            FactVerificationDecisionSchemaV08(
                decision_id=decision_id,
                candidate_id=candidate_id,
                decision=FactVerificationDecision.APPROVE,
                verification_method=VerificationMethod.DETERMINISTIC,
                verifier_identity="component:deterministic-verifier/0.8.0",
                verifier_response_id=None,
                reason_code="OFFICIAL_BLOCK_SUPPORTED",
                evidence_support_result=EvidenceSupportResult.SUPPORTED,
                precedence_check_result=PrecedenceCheckResult.PASSED,
                decided_at=NOW,
            )
        )
        lifecycle.promote(
            decision_ids=[decision_id],
            verified_fact_set_id=fact_set_id,
            reference_dataset_versions={"education_levels": "2026-08-24"},
            created_at=NOW,
        )
        session.commit()

    with Session(migrated_engine) as session:
        fact = session.scalar(
            select(VerifiedFact).where(VerifiedFact.verified_fact_set_id == fact_set_id)
        )
        assert fact is not None
        rule_candidate_id = uuid7()
        approval_id = uuid7()
        unit_rule_set_id = uuid7()
        promotion = RulePromotionService(session)
        promotion.propose(
            RuleCandidateSchemaV08(
                rule_candidate_id=rule_candidate_id,
                target_scope=ExtractionTargetScope.UNIT,
                opportunity_id=graph.opportunity_id,
                opportunity_version=1,
                opportunity_unit_id=graph.opportunity_unit_id,
                opportunity_unit_version_id=graph.opportunity_unit_version_id,
                verified_fact_ids=[fact.verified_fact_id],
                rule_type="ATOMIC_QUALIFICATION",
                proposed_rule_payload=ProposedRulePayloadSchemaV08.model_validate(
                    {
                        "code": "education-minimum",
                        "operator": "GTE",
                        "field": "education_level",
                        "value_type": "STRING",
                        "value": "BACHELOR",
                        "required": True,
                        "reason_template": "学历至少为本科",
                    }
                ),
                evidence_ref_ids=[graph.evidence_ref_id],
                compiler_version="p9b-rule-candidate-compiler/0.8.0",
                producer_identity="component:verified-fact-rule-candidate/0.8.0",
                status=RuleCandidateStatus.PROPOSED,
                created_at=NOW,
            ),
            verified_fact_set_id=fact_set_id,
        )
        promotion.decide(
            RuleApprovalDecisionSchemaV08(
                rule_approval_decision_id=approval_id,
                rule_candidate_id=rule_candidate_id,
                decision=RuleApprovalDecisionValue.APPROVE,
                approver_identity="component:rule-approval-policy/0.8.0",
                approval_method=RuleApprovalMethod.DETERMINISTIC_POLICY,
                reason_code="SUPPORTED_ATOMIC_RULE",
                decided_at=NOW,
                policy_version="p9b-rule-approval-policy/0.8.0",
            )
        )
        materialized = promotion.materialize_dormant_unit_rule_set(
            rule_candidate_id=rule_candidate_id,
            rule_approval_decision_id=approval_id,
            unit_rule_set_id=unit_rule_set_id,
            created_at=NOW,
        )
        assert materialized.activation_status == "DORMANT"
        assert session.scalar(select(func.count()).select_from(RuleSetModel)) == 0
        session.commit()

    with Session(migrated_engine) as session:
        assert session.get(UnitRuleSet, unit_rule_set_id) is not None
        dependency = session.scalar(
            select(VerifiedFactSetDependency).where(
                VerifiedFactSetDependency.verified_fact_set_id == fact_set_id,
                VerifiedFactSetDependency.dependency_type == "DOCUMENT_BLOCK",
            )
        )
        assert dependency is not None
        FactLifecycleService(session).invalidate_dependency(
            verified_fact_set_id=fact_set_id,
            dependency_id=dependency.dependency_id,
            observed_dependency_fingerprint="f" * 64,
            reason_code="SUCCESSOR_PARSE_IDENTITY",
            actor_identity="component:dependency-invalidator/0.8.0",
            created_at=NOW,
        )
        session.commit()

    with Session(migrated_engine) as session:
        fact_set = session.get(VersionedVerifiedFactSet, fact_set_id)
        assert fact_set is not None and fact_set.status == "STALE"
        transition = session.scalar(
            select(VerifiedFactSetTransition).where(
                VerifiedFactSetTransition.verified_fact_set_id == fact_set_id
            )
        )
        assert transition is not None and transition.to_status == "STALE"


def test_database_rejects_self_verification_and_fact_mutation(
    migrated_engine: Engine, object_store: S3ObjectStore
) -> None:
    graph = seed_fact_graph(migrated_engine, object_store)
    with Session(migrated_engine) as session:
        revision = session.get(SourceBundleRevision, graph.source_bundle_revision_id)
        assert revision is not None
        session.add(
            VersionedVerifiedFactSet(
                verified_fact_set_id=uuid7(),
                target_scope="UNIT",
                opportunity_id=graph.opportunity_id,
                opportunity_version=1,
                opportunity_unit_id=graph.opportunity_unit_id,
                opportunity_unit_version_id=graph.opportunity_unit_version_id,
                source_bundle_revision_id=graph.source_bundle_revision_id,
                version=1,
                relation_graph_version="wrong-relation-graph",
                precedence_graph_version=revision.precedence_graph_version,
                reference_dataset_versions={"education_levels": "2026-08-24"},
                fact_schema_version="0.8.0",
                status="ACTIVE",
                supersedes_id=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        with pytest.raises(DBAPIError, match="FACT_SET_BUNDLE_SNAPSHOT_MISMATCH"):
            session.flush()
        session.rollback()

    run_id = uuid7()
    candidate_id = uuid7()
    fact_set_id = uuid7()
    with Session(migrated_engine) as session:
        lifecycle = FactLifecycleService(session)
        lifecycle.persist_run(
            ExtractionRunSchemaV08(
                extraction_run_id=run_id,
                source_bundle_revision_id=graph.source_bundle_revision_id,
                target_scope=ExtractionTargetScope.UNIT,
                opportunity_id=graph.opportunity_id,
                opportunity_version=1,
                opportunity_unit_id=graph.opportunity_unit_id,
                opportunity_unit_version_id=graph.opportunity_unit_version_id,
                unit_segmentation_version="unit-segmentation/0.8.0",
                task_spec_version="p9b-extraction-task/0.8.0",
                extractor_kind=ExtractorKind.DETERMINISTIC,
                component_version="deterministic-fields/0.8.0",
                producer_identity="component:deterministic-fields/0.8.0",
                producer_response_id=None,
                ordered_input_block_ids=[graph.block_id],
                input_block_set_hash=extraction_input_block_set_hash([graph.block_id]),
                evidence_binding_hash=extraction_evidence_binding_hash(
                    [(graph.block_id, graph.evidence_binding_hash)]
                ),
                started_at=NOW,
                completed_at=NOW,
                status=ExtractionRunStatus.SUCCEEDED,
            )
        )
        lifecycle.record_candidate(
            ExtractionCandidateSchemaV08(
                candidate_id=candidate_id,
                extraction_run_id=run_id,
                target_scope=ExtractionTargetScope.UNIT,
                opportunity_id=graph.opportunity_id,
                opportunity_version=1,
                opportunity_unit_id=graph.opportunity_unit_id,
                opportunity_unit_version_id=graph.opportunity_unit_version_id,
                field_name="education_level",
                raw_value="BACHELOR",
                normalized_value_candidate="BACHELOR",
                evidence_block_ids=[graph.block_id],
                evidence_ref_ids=[graph.evidence_ref_id],
                confidence=1.0,
                abstained=False,
                candidate_reason_code="DETERMINISTIC_ENUM",
                schema_version="0.8.0",
                created_at=NOW,
            )
        )
        session.commit()

    with Session(migrated_engine) as session:
        session.add(
            FactVerificationDecisionModel(
                decision_id=uuid7(),
                candidate_id=candidate_id,
                decision=FactVerificationDecision.APPROVE,
                verification_method=VerificationMethod.DETERMINISTIC,
                verifier_identity="component:deterministic-fields/0.8.0",
                verifier_response_id=None,
                reason_code="SELF_APPROVAL",
                evidence_support_result=EvidenceSupportResult.SUPPORTED,
                precedence_check_result=PrecedenceCheckResult.PASSED,
                decided_at=NOW,
            )
        )
        with pytest.raises(DBAPIError, match="FACT_VERIFIER_NOT_INDEPENDENT"):
            session.flush()
        session.rollback()

    approved_decision_id = uuid7()
    with Session(migrated_engine) as session:
        FactLifecycleService(session).verify_candidate(
            FactVerificationDecisionSchemaV08(
                decision_id=approved_decision_id,
                candidate_id=candidate_id,
                decision=FactVerificationDecision.APPROVE,
                verification_method=VerificationMethod.DETERMINISTIC,
                verifier_identity="component:independent-verifier/0.8.0",
                verifier_response_id=None,
                reason_code="SUPPORTED",
                evidence_support_result=EvidenceSupportResult.SUPPORTED,
                precedence_check_result=PrecedenceCheckResult.PASSED,
                decided_at=NOW,
            )
        )
        FactLifecycleService(session).promote(
            decision_ids=[approved_decision_id],
            verified_fact_set_id=fact_set_id,
            reference_dataset_versions={"education_levels": "2026-08-24"},
            created_at=NOW,
        )
        session.commit()

    successor_fact_set_id = uuid7()
    with Session(migrated_engine) as session:
        FactLifecycleService(session).promote(
            decision_ids=[approved_decision_id],
            verified_fact_set_id=successor_fact_set_id,
            reference_dataset_versions={"education_levels": "2026-08-24.1"},
            created_at=NOW,
            supersedes_id=fact_set_id,
        )
        session.commit()

    with Session(migrated_engine) as session:
        predecessor = session.get(VersionedVerifiedFactSet, fact_set_id)
        successor = session.get(VersionedVerifiedFactSet, successor_fact_set_id)
        assert predecessor is not None and predecessor.status == "SUPERSEDED"
        assert successor is not None and successor.status == "ACTIVE" and successor.version == 2

    with (
        Session(migrated_engine) as session,
        pytest.raises(DBAPIError, match="immutable P9-B history"),
    ):
        session.execute(
            text(
                "update verified_facts set field_name = 'mutated' "
                "where verified_fact_set_id = :fact_set_id"
            ),
            {"fact_set_id": successor_fact_set_id},
        )


def test_unit_rule_set_is_not_referenced_by_legacy_eligibility_read_path() -> None:
    repository_root = Path(__file__).parents[2] / "src" / "deepaha"
    production_readers = (
        repository_root / "eligibility",
        repository_root / "public_catalog",
        repository_root / "personal",
        repository_root / "notifications",
        repository_root / "feedback",
    )
    for directory in production_readers:
        for path in directory.rglob("*.py"):
            source = path.read_text("utf-8")
            assert "UnitRuleSet" not in source
            assert "unit_rule_sets" not in source
