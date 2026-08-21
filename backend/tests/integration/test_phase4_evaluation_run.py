from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.documents.models import EvidenceRef
from deepaha.eligibility.service import EligibilityService, MatchInput
from deepaha.evaluation.fixtures import FixtureBundle, GoldenCaseFixture, load_fixture_bundle
from deepaha.evaluation.models import EvaluationCaseResultModel, EvaluationRunModel
from deepaha.evaluation.runner import (
    CaseEvaluation,
    persist_evaluation_run,
    run_synthetic_evaluation,
)
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.rules.models import RuleEvidenceModel, RuleModel, RuleSetModel
from tests.integration.test_phase4_persistence_contract import persist_phase3_inputs

pytestmark = pytest.mark.integration
FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def fixture_bundle() -> FixtureBundle:
    return load_fixture_bundle(FIXTURE_DIRECTORY)


@pytest.fixture
def phase4_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(migrated_engine, expire_on_commit=False)


def test_fixed_golden_dataset_replays_through_real_engine_and_persists(
    fixture_bundle: FixtureBundle,
    phase4_session_factory: sessionmaker[Session],
) -> None:
    evaluator = _seed_real_case_evaluator(fixture_bundle, phase4_session_factory)

    report = run_synthetic_evaluation(fixture_bundle, evaluator)

    assert report.metrics.case_count == 12
    assert report.metrics.passed_case_count == 12
    assert report.metrics.unexpected_ineligible_count == 0
    assert report.metrics.unexpected_ineligible_case_ids == ()
    assert report.evidence_label == "SYNTHETIC_EVALUATION_ONLY"

    run_id = uuid7()
    with phase4_session_factory() as session:
        contract = persist_evaluation_run(
            session,
            report,
            run_id=run_id,
            started_at=NOW,
            completed_at=NOW,
        )
        session.commit()

    assert contract.run_id == run_id
    assert contract.synthetic is True
    assert contract.metrics is not None
    assert contract.metrics.unexpected_ineligible_count == 0
    assert len(contract.case_results) == 12
    with phase4_session_factory() as session:
        stored = session.get(EvaluationRunModel, run_id)
        assert stored is not None
        assert stored.evidence_label == "SYNTHETIC_EVALUATION_ONLY"
        assert stored.scenario_clock == fixture_bundle.scenario_clock
        assert stored.report_sha256 == report.report_sha256
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvaluationCaseResultModel)
                .where(EvaluationCaseResultModel.run_id == run_id)
            )
            == 12
        )


def _seed_real_case_evaluator(
    bundle: FixtureBundle,
    factory: sessionmaker[Session],
) -> Callable[[GoldenCaseFixture], CaseEvaluation]:
    match_inputs: dict[str, MatchInput] = {}
    profiles = {
        profile.snapshot.profile_snapshot_id: profile
        for profile in bundle.mother_profiles + bundle.synthetic_profiles
    }
    with factory() as session:
        opportunity, version, source_evidence = persist_phase3_inputs(session)
        for rule_set_version, case in enumerate(
            sorted(bundle.golden_cases, key=lambda item: item.case_id),
            start=1,
        ):
            fixture_profile = profiles[case.profile_snapshot_id].snapshot
            if session.get(ProfileSnapshotModel, fixture_profile.profile_snapshot_id) is None:
                session.add(
                    ProfileSnapshotModel(
                        profile_snapshot_id=fixture_profile.profile_snapshot_id,
                        profile_id=fixture_profile.profile_id,
                        version=fixture_profile.version,
                        synthetic=fixture_profile.synthetic,
                        persona_family_id=fixture_profile.persona_family_id,
                        attributes=fixture_profile.attributes.model_dump(mode="json"),
                        scenario_clock=fixture_profile.scenario_clock,
                        profile_schema_version=fixture_profile.profile_schema_version,
                        created_at=fixture_profile.created_at,
                        created_by=fixture_profile.created_by,
                        reviewed_by=fixture_profile.reviewed_by,
                        change_note=fixture_profile.change_note,
                    )
                )
                session.flush()
            rule_id = uuid7()
            rule_set = RuleSetModel(
                rule_set_id=uuid7(),
                version=rule_set_version,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=version.version,
                root_rule_ids=[str(rule_id)],
                review_status="APPROVED",
                rule_schema_version="0.4.0",
                created_at=NOW,
            )
            session.add(rule_set)
            session.flush()
            session.add(
                RuleModel(
                    rule_set_id=rule_set.rule_set_id,
                    rule_set_version=rule_set.version,
                    rule_id=rule_id,
                    code=case.rule.code,
                    operator=case.rule.operator.value,
                    field=case.rule.field.value,
                    value_type=case.rule.value_type.value,
                    value=case.rule.value,
                    operand_rule_ids=[],
                    required=True,
                    reason_template=f"Synthetic Golden rule: {case.case_id}",
                )
            )
            session.flush()
            for evidence_index, evidence in enumerate(case.rule.evidence):
                evidence_ref = source_evidence
                if evidence_index:
                    evidence_ref = EvidenceRef(
                        evidence_ref_id=uuid7(),
                        document_id=source_evidence.document_id,
                        artifact_id=source_evidence.artifact_id,
                        locator_kind="paragraph",
                        locator_value=f"synthetic-{case.case_id}-{evidence_index}",
                        locator_schema_version="0.1.0",
                        locator_payload=None,
                        quote_sha256=sha256(
                            f"{case.case_id}:{evidence_index}".encode()
                        ).hexdigest(),
                    )
                    session.add(evidence_ref)
                    session.flush()
                session.add(
                    RuleEvidenceModel(
                        rule_set_id=rule_set.rule_set_id,
                        rule_set_version=rule_set.version,
                        rule_id=rule_id,
                        evidence_ref_id=evidence_ref.evidence_ref_id,
                        document_id=evidence_ref.document_id,
                        authority=evidence.authority.value,
                        precedence=evidence.authority.precedence,
                        relation=evidence.relation.value,
                        effective_at=NOW,
                        assertion_sha256=sha256(
                            f"assertion:{case.case_id}:{evidence_index}".encode()
                        ).hexdigest(),
                    )
                )
            session.flush()
            match_inputs[case.case_id] = MatchInput(
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=version.version,
                rule_set_id=rule_set.rule_set_id,
                rule_set_version=rule_set.version,
                profile_snapshot_id=fixture_profile.profile_snapshot_id,
                major_catalog=bundle.major_catalog,
                major_mapping=bundle.major_mapping,
                evaluated_at=NOW,
                created_at=NOW,
                semantic_major_candidate=case.semantic_major_candidate,
            )
        session.commit()

    service = EligibilityService(session_factory=factory, id_factory=uuid7)

    def evaluate(case: GoldenCaseFixture) -> CaseEvaluation:
        snapshot = service.evaluate_and_save(match_inputs[case.case_id])
        replayed = service.replay(snapshot.snapshot_id)
        return CaseEvaluation(
            actual_status=snapshot.eligibility_result.status,
            match_snapshot_id=snapshot.snapshot_id,
            input_sha256=snapshot.input_sha256,
            reason_codes=tuple(
                sorted(
                    {
                        evaluation.reason_code
                        for evaluation in snapshot.eligibility_result.rule_evaluations
                    }
                )
            ),
            replay_matched=(
                replayed.model_dump(mode="json") == snapshot.model_dump(mode="json")
            ),
        )

    return evaluate
