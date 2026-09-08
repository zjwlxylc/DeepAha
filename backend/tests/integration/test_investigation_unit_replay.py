"""Synthetic DB-to-engine seam replay; no real human or release qualification evidence."""

import json
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid7

import pytest

from deepaha.contracts.phase4 import ProfileSnapshotSchemaV04
from deepaha.investigations.unit_snapshots import load_unit_plan, materialize_unit_plan
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.rules.major import load_approved_major_mapping, load_major_catalog
from deepaha.unit_qualification.contracts import UnitIdentity, UnitQualificationPlan
from deepaha.unit_qualification.evaluator import UnitEvaluationInput, evaluate_unit_qualification
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.integration.test_investigation_unit_coverage import _heterogeneous
from tests.integration.test_investigation_unit_snapshots import approved, ready

__all__ = ["harness"]
pytestmark = pytest.mark.integration
ASSETS = Path(__file__).parents[1] / "fixtures" / "evaluation"


def _profile(h: StoreHarness, education: str | None) -> ProfileSnapshotSchemaV04:
    payload = json.loads((ASSETS / "phase4-mother-profiles.json").read_text())["profiles"][0][
        "snapshot"
    ]
    payload.update(
        profile_snapshot_id=str(uuid7()),
        profile_id=str(uuid7()),
        scenario_clock=h.clock().date().isoformat(),
        created_at=h.clock().isoformat(),
        created_by="synthetic-unit-replay-fixture",
        reviewed_by="synthetic-unit-replay-checks",
        change_note="Synthetic engineering fixture only; not a real participant",
    )
    payload["attributes"]["education_level"] = education
    profile = ProfileSnapshotSchemaV04.model_validate(payload)
    assert profile.synthetic
    values = profile.model_dump()
    values["attributes"] = profile.attributes.model_dump(mode="json")
    with h.factory.begin() as session:
        session.add(ProfileSnapshotModel(**values))
    with h.factory() as session:
        stored = session.get(ProfileSnapshotModel, profile.profile_snapshot_id)
        assert stored is not None and stored.synthetic
        return ProfileSnapshotSchemaV04.model_validate(
            {key: getattr(stored, key) for key in ProfileSnapshotSchemaV04.model_fields}
        )


def _input(
    snapshot: dict[str, Any], profile: ProfileSnapshotSchemaV04, h: StoreHarness
) -> UnitEvaluationInput:
    plan = UnitQualificationPlan.model_validate(snapshot["plan"])
    catalog = load_major_catalog(ASSETS / "phase4-major-catalog.json")
    return UnitEvaluationInput(
        plan=plan,
        expected_target=plan.target,
        profile_snapshot_id=profile.profile_snapshot_id,
        profile_version=profile.version,
        profile_schema_version=profile.profile_schema_version,
        profile_attributes=profile.attributes.model_dump(mode="json"),
        major_catalog=catalog,
        major_mapping=load_approved_major_mapping(ASSETS / "phase4-major-mapping.json", catalog),
        scenario_clock=profile.scenario_clock,
        evidence_as_of=h.clock(),
    )


def _record(tmp_path: Path, name: str, snapshot: dict[str, Any], cases: list[Any]) -> None:
    # Every run writes only into pytest's disposable per-test directory. An audited
    # copy may be retained as evidence; the file is never consumed as DB admission.
    backend = Path(__file__).parents[2]
    inputs = [
        "src/deepaha/investigations/unit_snapshots.py",
        "src/deepaha/investigations/unit_manifest.py",
        "src/deepaha/unit_qualification/contracts.py",
        "src/deepaha/unit_qualification/compiler.py",
        "src/deepaha/unit_qualification/evaluator.py",
        "src/deepaha/eligibility/engine.py",
        "tests/integration/test_investigation_unit_replay.py",
    ]
    report = {
        "mode": "SYNTHETIC_DATABASE_TO_ENGINE_REPLAY_ONLY",
        "wma_calls": 0,
        "official_source_requests": 0,
        "real_participants": 0,
        "real_human_approvals": 0,
        "fixture_database_writes": True,
        "code_hash_normalization": "CRLF_TO_LF",
        "input_files": {
            path: sha256((backend / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in inputs
        },
        "major_catalog": json.loads((ASSETS / "phase4-major-catalog.json").read_text()),
        "major_mapping": json.loads((ASSETS / "phase4-major-mapping.json").read_text()),
        "trusted_snapshot": snapshot,
        "cases": cases,
    }
    (tmp_path / f"{name}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )


def test_persisted_profiles_replay_current_snapshot_with_traceable_rule_outcomes(
    harness: StoreHarness, tmp_path: Path
) -> None:
    h = harness
    task, command = approved(h)
    snapshot = materialize_unit_plan(h.store, task, command, h.principal)
    cases = []
    input_hashes = set()
    for education, expected_engine, expected_rule in [
        ("MASTER", "ELIGIBLE", "SATISFIED"),
        ("BACHELOR", "INELIGIBLE", "CONFLICT"),
        (None, "UNCERTAIN", "UNKNOWN"),
    ]:
        profile = _profile(h, education)
        current = load_unit_plan(h.store, task, UUID(snapshot["plan_id"]), h.principal)
        assert current == snapshot
        request = _input(current, profile, h)
        first = evaluate_unit_qualification(request)
        assert evaluate_unit_qualification(request) == first
        assert first.target == request.expected_target
        assert first.engine_status == expected_engine and first.status == "UNCERTAIN"
        assert first.status_cap == "UNCERTAIN"
        assert "HUMAN_SCOPE_REVIEW_UNVERIFIED" in first.review_reasons
        assert "SOURCE_COMPLETENESS_UNVERIFIED" in first.review_reasons
        rule = request.plan.rules[0]
        evaluation = first.rule_evaluations[0]
        assert evaluation.rule_id == rule.rule_id and evaluation.outcome == expected_rule
        assert evaluation.evidence_ref_ids == tuple(e.evidence_ref_id for e in rule.evidence)
        # For missing profile values the engine retains official reference IDs,
        # but does not assert an official, deterministic comparison conclusion.
        assert evaluation.official_evidence is (education is not None)
        assert evaluation.deterministic is (education is not None)
        assert first.missing_fields == (() if education else ("education_level",))
        if education == "BACHELOR":
            assert first.conflict_rule_ids == (rule.rule_id,)
            assert "NEGATIVE_CONCLUSION_REQUIRES_SCOPE_REVIEW" in first.review_reasons
        input_hashes.add(first.input_sha256)
        cases.append({"profile": profile.model_dump(mode="json"), "result": asdict(first)})
    assert len(input_hashes) == 3
    _record(tmp_path, "persisted-profile-matrix", snapshot, cases)


def test_unknown_official_condition_cannot_be_filled_by_complete_profile(
    harness: StoreHarness, tmp_path: Path
) -> None:
    h = harness
    task, command, _ = ready(h, unknown=True)
    snapshot = materialize_unit_plan(h.store, task, command, h.principal)
    current = load_unit_plan(h.store, task, UUID(snapshot["plan_id"]), h.principal)
    profile = _profile(h, "DOCTORATE")
    request = _input(current, profile, h)
    result = evaluate_unit_qualification(request)
    assert result.status == result.engine_status == "UNCERTAIN"
    assert result.rule_evaluations == result.satisfied_rule_ids == ()
    assert request.plan.manifest.conditions[0].state == "UNKNOWN"
    assert any(b.condition_id for b in result.coverage_blockers)
    _record(
        tmp_path,
        "unknown-condition",
        current,
        [{"profile": profile.model_dump(mode="json"), "result": asdict(result)}],
    )


def test_multi_scope_snapshot_preserves_unresolved_conditions_during_evaluation(
    harness: StoreHarness, tmp_path: Path
) -> None:
    h = harness
    task, command, _ = _heterogeneous(h)
    snapshot = materialize_unit_plan(h.store, task, command, h.principal)
    current = load_unit_plan(h.store, task, UUID(snapshot["plan_id"]), h.principal)
    profile = _profile(h, "DOCTORATE")
    request = _input(current, profile, h)
    result = evaluate_unit_qualification(request)
    assert result.engine_status == "ELIGIBLE" and result.status == "UNCERTAIN"
    assert len(result.satisfied_rule_ids) == 1
    blocked_ids = {b.condition_id for b in result.coverage_blockers if b.condition_id}
    unresolved = {c.condition_id for c in request.plan.manifest.conditions if c.state != "KNOWN"}
    assert unresolved <= blocked_ids
    assert "SOURCE_NOTES_UNREVIEWED" in result.review_reasons
    assert len(request.plan.manifest.conditions) == 7
    assert current["context"]["source_row_count"] == 9
    assert current == snapshot  # Evaluation must not rewrite the source/audit context.
    _record(
        tmp_path,
        "multi-scope-conditions",
        current,
        [{"profile": profile.model_dump(mode="json"), "result": asdict(result)}],
    )


@pytest.mark.parametrize(
    "field", ["opportunity_id", "opportunity_version", "unit_id", "unit_version", "unit_version_id"]
)
def test_target_mismatch_is_rejected_before_profile_comparison(
    harness: StoreHarness, field: str
) -> None:
    h = harness
    task, command = approved(h)
    snapshot = materialize_unit_plan(h.store, task, command, h.principal)
    current = load_unit_plan(h.store, task, UUID(snapshot["plan_id"]), h.principal)
    request = _input(current, _profile(h, "MASTER"), h)
    target = request.expected_target.model_dump()
    target[field] = target[field] + 1 if field.endswith("version") else uuid7()
    with pytest.raises(ValueError, match="requested target differs"):
        evaluate_unit_qualification(replace(request, expected_target=UnitIdentity(**target)))
