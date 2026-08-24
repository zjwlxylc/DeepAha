from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef
from deepaha.documents.parser import LEGACY_PARSE_CONTRACT_VERSION
from deepaha.eligibility.models import EligibilityResultModel
from deepaha.evaluation.models import EvaluationCaseResultModel, EvaluationRunModel
from deepaha.matching.models import MatchSnapshotModel
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.hashing import document_parse_key
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.rules.models import RuleEvidenceModel, RuleModel, RuleSetModel
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
TODAY = date(2026, 8, 22)
SHA_ONE = "1" * 64
SHA_TWO = "2" * 64
PHASE4_TABLES = {
    "rule_sets",
    "rules",
    "rule_evidence",
    "profile_snapshots",
    "eligibility_results",
    "match_snapshots",
    "evaluation_runs",
    "evaluation_case_results",
}
BACKEND_ROOT = Path(__file__).parents[2]


def persist_phase3_inputs(
    session: Session,
) -> tuple[Opportunity, OpportunityVersion, EvidenceRef]:
    source_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url="https://phase4-persistence.example.gov/",
        authority_name="Synthetic Phase 4 Authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction=None,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    artifact = RawArtifact(
        artifact_id=uuid7(),
        source_id=source.source_id,
        requested_url="https://phase4-persistence.example.gov/notices/1",
        resolved_url="https://phase4-persistence.example.gov/notices/1",
        retrieved_at=NOW,
        http_status=200,
        media_type="text/html",
        content_sha256=SHA_ONE,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{SHA_ONE[:2]}/{SHA_ONE}",
        byte_size=128,
        collector_version="phase4-test/0.4.0",
        metadata_schema_version="0.2.0",
    )
    document = Document(
        document_id=uuid7(),
        artifact_id=artifact.artifact_id,
        title="Synthetic Phase 4 notice",
        published_at=NOW,
        language="und",
        extracted_text_uri=None,
        parser_name="phase4_synthetic",
        parser_version="0.4.0",
        parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        document_parse_key=document_parse_key(
            artifact_id=artifact.artifact_id,
            artifact_sha256=artifact.content_sha256,
            parser_name="phase4_synthetic",
            parser_version="0.4.0",
            parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        ),
        parse_confidence=None,
        created_at=NOW,
    )
    evidence = EvidenceRef(
        evidence_ref_id=uuid7(),
        document_id=document.document_id,
        artifact_id=artifact.artifact_id,
        locator_kind="full_document",
        locator_value="*",
        locator_schema_version="0.1.0",
        locator_payload=None,
        quote_sha256=SHA_ONE,
    )
    opportunity_id = uuid7()
    opportunity = Opportunity(
        opportunity_id=opportunity_id,
        public_id=f"opp_{opportunity_id.hex}",
        type="YOUTH_DEVELOPMENT_PROGRAM",
        canonical_title="Synthetic Phase 4 opportunity",
        issuer_name="Synthetic Phase 4 Authority",
        jurisdiction=None,
        current_version=None,
        status="OPEN",
        publication_status="INTERNAL",
        created_at=NOW,
        updated_at=NOW,
    )
    version = OpportunityVersion(
        opportunity_id=opportunity.opportunity_id,
        version=1,
        effective_from=NOW,
        source_document_id=document.document_id,
        source_evidence_ref_id=evidence.evidence_ref_id,
        snapshot={
            "canonical_title": opportunity.canonical_title,
            "type": opportunity.type,
            "issuer_name": opportunity.issuer_name,
            "jurisdiction": None,
            "status": opportunity.status,
            "published_at": NOW.isoformat(),
            "application_window": {"opens_on": None, "closes_on": None, "timezone": None},
            "application_url": None,
            "attachment_urls": [],
            "locations": [],
        },
        field_evidence=[
            {
                "field_path": "canonical_title",
                "precedence": 400,
                "evidence_ref_id": str(evidence.evidence_ref_id),
                "effective_at": NOW.isoformat(),
            }
        ],
        changes=[
            {
                "field_path": "canonical_title",
                "before": None,
                "after": opportunity.canonical_title,
                "evidence_ref_id": str(evidence.evidence_ref_id),
            }
        ],
        content_sha256=SHA_TWO,
        review_status="NOT_REQUIRED",
        created_at=NOW,
    )
    session.add(source)
    session.flush()
    session.add(artifact)
    session.flush()
    session.add_all([document, opportunity])
    session.flush()
    session.add(evidence)
    session.flush()
    session.add(version)
    session.flush()
    return opportunity, version, evidence


def persist_phase4_inputs(
    session: Session,
) -> tuple[RuleSetModel, ProfileSnapshotModel, RuleModel, RuleEvidenceModel]:
    opportunity, version, evidence_ref = persist_phase3_inputs(session)
    rule_id = uuid7()
    rule_set = RuleSetModel(
        rule_set_id=uuid7(),
        version=1,
        opportunity_id=opportunity.opportunity_id,
        opportunity_version=version.version,
        root_rule_ids=[str(rule_id)],
        review_status="APPROVED",
        rule_schema_version="0.4.0",
        created_at=NOW,
    )
    session.add(rule_set)
    session.flush()
    rule = RuleModel(
        rule_set_id=rule_set.rule_set_id,
        rule_set_version=rule_set.version,
        rule_id=rule_id,
        code="education-bachelor",
        operator="IN",
        field="education_level",
        value_type="STRING",
        value=["BACHELOR", "DOCTORATE", "MASTER"],
        operand_rule_ids=[],
        required=True,
        reason_template="Synthetic education rule",
    )
    session.add(rule)
    session.flush()
    evidence = RuleEvidenceModel(
        rule_set_id=rule_set.rule_set_id,
        rule_set_version=rule_set.version,
        rule_id=rule.rule_id,
        evidence_ref_id=evidence_ref.evidence_ref_id,
        document_id=evidence_ref.document_id,
        authority="ORIGINAL_OFFICIAL_NOTICE",
        precedence=400,
        relation="SUPPORTS",
        effective_at=NOW,
        assertion_sha256=SHA_ONE,
    )
    profile = ProfileSnapshotModel(
        profile_snapshot_id=uuid7(),
        profile_id=uuid7(),
        version=1,
        synthetic=True,
        persona_family_id=None,
        attributes={
            "education_level": "BACHELOR",
            "major_name": "Synthetic software engineering",
            "major_code": "080902",
            "graduation_year": 2026,
            "student_status": "GRADUATING",
            "birth_date": "2003-08-22",
            "hukou_region": "Synthetic-Zhejiang",
            "residence_region": "Synthetic-Hangzhou",
            "target_regions": ["Synthetic-Hangzhou"],
            "certificates": ["CET4"],
        },
        scenario_clock=TODAY,
        profile_schema_version="0.4.0",
        created_at=NOW,
        created_by="phase4-fixture-generator",
        reviewed_by="phase4-fixture-governance",
        change_note="Synthetic persistence contract",
    )
    session.add_all([evidence, profile])
    session.flush()
    return rule_set, profile, rule, evidence


def persist_complete_phase4_graph(
    session: Session,
) -> tuple[RuleSetModel, ProfileSnapshotModel, MatchSnapshotModel, EvaluationRunModel]:
    rule_set, profile, rule, evidence = persist_phase4_inputs(session)
    result = EligibilityResultModel(
        result_id=uuid7(),
        opportunity_id=rule_set.opportunity_id,
        opportunity_version=rule_set.opportunity_version,
        rule_set_id=rule_set.rule_set_id,
        rule_set_version=rule_set.version,
        profile_snapshot_id=profile.profile_snapshot_id,
        status="ELIGIBLE",
        rule_results=[
            {
                "rule_id": str(rule.rule_id),
                "outcome": "SATISFIED",
                "deterministic": True,
                "official_evidence": True,
                "reason_code": "RULE_SATISFIED",
                "evidence_ref_ids": [str(evidence.evidence_ref_id)],
                "missing_fields": [],
            }
        ],
        satisfied_rule_ids=[str(rule.rule_id)],
        conflict_rule_ids=[],
        unknown_rule_ids=[],
        missing_fields=[],
        review_reasons=[],
        evaluated_at=NOW,
        engine_version="phase4-engine-v1",
    )
    session.add(result)
    session.flush()
    match = MatchSnapshotModel(
        snapshot_id=uuid7(),
        eligibility_result_id=result.result_id,
        opportunity_id=result.opportunity_id,
        opportunity_version=result.opportunity_version,
        rule_set_id=result.rule_set_id,
        rule_set_version=result.rule_set_version,
        profile_snapshot_id=result.profile_snapshot_id,
        profile_version=profile.version,
        compiler_version="phase4-compiler-v1",
        engine_version=result.engine_version,
        major_catalog_version="phase4-synthetic-major-catalog-v1",
        major_mapping_version="phase4-synthetic-major-mapping-v1",
        scenario_clock=TODAY,
        input_sha256=SHA_ONE,
        created_at=NOW,
    )
    session.add(match)
    session.flush()
    run = EvaluationRunModel(
        run_id=uuid7(),
        dataset_id="phase4-golden-synthetic",
        dataset_version="v1",
        dataset_sha256=SHA_TWO,
        evidence_label="SYNTHETIC_EVALUATION_ONLY",
        scenario_clock=NOW,
        report_sha256="3" * 64,
        component="ELIGIBILITY",
        component_versions={
            "contract": "0.4.0",
            "compiler": "phase4-compiler-v1",
            "engine": "phase4-engine-v1",
            "major_catalog": "phase4-synthetic-major-catalog-v1",
            "major_mapping": "phase4-synthetic-major-mapping-v1",
        },
        synthetic=True,
        status="COMPLETED",
        metrics={
            "total_cases": 1,
            "passed_cases": 1,
            "expected_ineligible_count": 0,
            "actual_ineligible_count": 0,
            "unexpected_ineligible_count": 0,
            "unexpected_ineligible_case_ids": [],
            "replay_mismatch_count": 0,
            "status_counts": {
                "ELIGIBLE": 1,
                "LIKELY_ELIGIBLE": 0,
                "UNCERTAIN": 0,
                "INELIGIBLE": 0,
            },
        },
        started_at=NOW,
        completed_at=NOW,
        error_summary=None,
    )
    session.add(run)
    session.flush()
    session.add(
        EvaluationCaseResultModel(
            run_id=run.run_id,
            case_id="phase4-case-001",
            expected_status="ELIGIBLE",
            actual_status="ELIGIBLE",
            passed=True,
            match_snapshot_id=match.snapshot_id,
            input_sha256=match.input_sha256,
            unexpected_ineligible=False,
            reason_codes=["RULE_SATISFIED"],
        )
    )
    session.flush()
    return rule_set, profile, match, run


def test_phase4_tables_exist(migrated_engine: Engine) -> None:
    assert set(inspect(migrated_engine).get_table_names()) >= PHASE4_TABLES


def test_complete_versioned_graph_persists(session: Session) -> None:
    _, _, match, run = persist_complete_phase4_graph(session)
    assert match.input_sha256 == SHA_ONE
    assert run.status == "COMPLETED"


def test_rule_set_identity_and_version_are_unique(session: Session) -> None:
    rule_set, _, _, _ = persist_phase4_inputs(session)
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                """
                INSERT INTO rule_sets (
                    rule_set_id, version, opportunity_id, opportunity_version,
                    root_rule_ids, review_status, rule_schema_version, created_at
                ) SELECT
                    rule_set_id, version, opportunity_id, opportunity_version,
                    root_rule_ids, review_status, rule_schema_version, created_at
                FROM rule_sets
                WHERE rule_set_id = :rule_set_id AND version = :version
                """
            ),
            {"rule_set_id": rule_set.rule_set_id, "version": rule_set.version},
        )
        session.flush()


def test_profile_identity_version_is_unique_and_real_profile_is_rejected(
    session: Session,
) -> None:
    _, profile, _, _ = persist_phase4_inputs(session)
    session.add(
        ProfileSnapshotModel(
            profile_snapshot_id=uuid7(),
            profile_id=profile.profile_id,
            version=profile.version,
            synthetic=True,
            persona_family_id=None,
            attributes={},
            scenario_clock=TODAY,
            profile_schema_version="0.4.0",
            created_at=NOW,
            created_by="phase4-test",
            reviewed_by="phase4-test",
            change_note="Duplicate profile version",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()
    session.add(
        ProfileSnapshotModel(
            profile_snapshot_id=uuid7(),
            profile_id=uuid7(),
            version=1,
            synthetic=False,
            persona_family_id=None,
            attributes={},
            scenario_clock=TODAY,
            profile_schema_version="0.4.0",
            created_at=NOW,
            created_by="phase4-test",
            reviewed_by="phase4-test",
            change_note="Real profiles are outside Phase 4",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_match_input_hash_is_unique(session: Session) -> None:
    _, _, match, _ = persist_complete_phase4_graph(session)
    original_result = session.get(EligibilityResultModel, match.eligibility_result_id)
    assert original_result is not None
    duplicate_result = EligibilityResultModel(
        result_id=uuid7(),
        opportunity_id=original_result.opportunity_id,
        opportunity_version=original_result.opportunity_version,
        rule_set_id=original_result.rule_set_id,
        rule_set_version=original_result.rule_set_version,
        profile_snapshot_id=original_result.profile_snapshot_id,
        status=original_result.status,
        rule_results=original_result.rule_results,
        satisfied_rule_ids=original_result.satisfied_rule_ids,
        conflict_rule_ids=original_result.conflict_rule_ids,
        unknown_rule_ids=original_result.unknown_rule_ids,
        missing_fields=original_result.missing_fields,
        review_reasons=original_result.review_reasons,
        evaluated_at=original_result.evaluated_at,
        engine_version=original_result.engine_version,
    )
    session.add(duplicate_result)
    session.flush()
    session.add(
        MatchSnapshotModel(
            snapshot_id=uuid7(),
            eligibility_result_id=duplicate_result.result_id,
            opportunity_id=match.opportunity_id,
            opportunity_version=match.opportunity_version,
            rule_set_id=match.rule_set_id,
            rule_set_version=match.rule_set_version,
            profile_snapshot_id=match.profile_snapshot_id,
            profile_version=match.profile_version,
            compiler_version=match.compiler_version,
            engine_version=match.engine_version,
            major_catalog_version=match.major_catalog_version,
            major_mapping_version=match.major_mapping_version,
            scenario_clock=match.scenario_clock,
            input_sha256=match.input_sha256,
            created_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_referenced_profile_cannot_be_deleted(session: Session) -> None:
    _, profile, _, _ = persist_complete_phase4_graph(session)
    with pytest.raises(IntegrityError):
        session.execute(
            delete(ProfileSnapshotModel).where(
                ProfileSnapshotModel.profile_snapshot_id == profile.profile_snapshot_id
            )
        )
        session.flush()


def test_downgrade_refuses_to_drop_nonempty_phase4_tables(migrated_engine: Engine) -> None:
    snapshot_id = uuid7()
    profile_id = uuid7()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profile_snapshots (
                    profile_snapshot_id, profile_id, version, synthetic,
                    persona_family_id, attributes, scenario_clock,
                    profile_schema_version, created_at, created_by,
                    reviewed_by, change_note
                ) VALUES (
                    :snapshot_id, :profile_id, 1, true,
                    null, '{}'::jsonb, :scenario_clock,
                    '0.4.0', :created_at, 'phase4-test',
                    'phase4-test', 'Downgrade protection'
                )
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "profile_id": profile_id,
                "scenario_clock": TODAY,
                "created_at": NOW,
            },
        )
    with pytest.raises(RuntimeError, match="candidate rows exist"):
        command.downgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "20260822_0003")
    with migrated_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM profile_snapshots WHERE profile_snapshot_id = :snapshot_id"),
            {"snapshot_id": snapshot_id},
        )
