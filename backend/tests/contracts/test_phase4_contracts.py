import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from deepaha.contracts.export import (
    PHASE4_SCHEMAS,
    render_phase1_schemas,
    render_phase2_schemas,
    render_phase3_schemas,
    render_phase4_schemas,
    write_phase4_schemas,
)
from deepaha.contracts.phase4 import (
    EducationLevel,
    EligibilityResultSchemaV04,
    EligibilityStatus,
    EvaluationRunSchemaV04,
    MatchSnapshotSchemaV04,
    ProfileSnapshotSchemaV04,
    RuleEvidenceAuthority,
    RuleEvidenceSchemaV04,
    RuleOperator,
    RuleSchemaV04,
    RuleSetSchemaV04,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
V01_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.1.0"
V02_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.2.0"
V03_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.3.0"
V04_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.4.0"
V04_EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.4.0" / "phase-4-example.json"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
RULE_SET_ID = UUID("019b0000-0000-7000-8000-000000000101")
RULE_ID = UUID("019b0000-0000-7000-8000-000000000102")
EVIDENCE_REF_ID = UUID("019b0000-0000-7000-8000-000000000103")
DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000000104")
OPPORTUNITY_ID = UUID("019b0000-0000-7000-8000-000000000105")
PROFILE_SNAPSHOT_ID = UUID("019b0000-0000-7000-8000-000000000106")
PROFILE_ID = UUID("019b0000-0000-7000-8000-000000000107")
RESULT_ID = UUID("019b0000-0000-7000-8000-000000000108")
MATCH_SNAPSHOT_ID = UUID("019b0000-0000-7000-8000-000000000109")
RUN_ID = UUID("019b0000-0000-7000-8000-000000000110")


def evidence_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "evidence_ref_id": EVIDENCE_REF_ID,
        "document_id": DOCUMENT_ID,
        "authority": "ORIGINAL_OFFICIAL_NOTICE",
        "precedence": 400,
        "relation": "SUPPORTS",
        "effective_at": NOW,
        "assertion_sha256": "1" * 64,
    }
    values.update(changes)
    return values


def rule_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "rule_id": RULE_ID,
        "code": "education-bachelor",
        "operator": "IN",
        "field": "education_level",
        "value_type": "STRING",
        "value": ["BACHELOR", "DOCTORATE", "MASTER"],
        "operand_rule_ids": [],
        "required": True,
        "reason_template": "Education must be at least bachelor level.",
        "evidence": [evidence_values()],
    }
    values.update(changes)
    return values


def rule_set_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "rule_set_id": RULE_SET_ID,
        "version": 1,
        "opportunity_id": OPPORTUNITY_ID,
        "opportunity_version": 1,
        "rules": [rule_values()],
        "root_rule_ids": [RULE_ID],
        "review_status": "APPROVED",
        "rule_schema_version": "0.4.0",
        "created_at": NOW,
    }
    values.update(changes)
    return values


def profile_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "profile_snapshot_id": PROFILE_SNAPSHOT_ID,
        "profile_id": PROFILE_ID,
        "version": 1,
        "synthetic": True,
        "persona_family_id": None,
        "attributes": {
            "education_level": "BACHELOR",
            "major_name": "Synthetic software engineering",
            "major_code": "080902",
            "graduation_year": 2026,
            "student_status": "GRADUATING",
            "birth_date": "2003-08-22",
            "hukou_region": "Synthetic-Zhejiang",
            "residence_region": "Synthetic-Hangzhou",
            "target_regions": ["Synthetic-Hangzhou", "Synthetic-Ningbo"],
            "certificates": ["CET4"],
        },
        "scenario_clock": "2026-08-22",
        "profile_schema_version": "0.4.0",
        "created_at": NOW,
        "created_by": "phase4-fixture-generator",
        "reviewed_by": "phase4-fixture-governance",
        "change_note": "Synthetic contract example only.",
    }
    values.update(changes)
    return values


def rule_evaluation_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "rule_id": RULE_ID,
        "outcome": "SATISFIED",
        "deterministic": True,
        "official_evidence": True,
        "reason_code": "RULE_SATISFIED",
        "evidence_ref_ids": [EVIDENCE_REF_ID],
        "missing_fields": [],
    }
    values.update(changes)
    return values


def result_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "result_id": RESULT_ID,
        "status": "ELIGIBLE",
        "rule_evaluations": [rule_evaluation_values()],
        "satisfied_rule_ids": [RULE_ID],
        "conflict_rule_ids": [],
        "unknown_rule_ids": [],
        "missing_fields": [],
        "review_reasons": [],
        "evaluated_at": NOW,
        "engine_version": "phase4-engine-v1",
    }
    values.update(changes)
    return values


def match_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "snapshot_id": MATCH_SNAPSHOT_ID,
        "opportunity_id": OPPORTUNITY_ID,
        "opportunity_version": 1,
        "rule_set_id": RULE_SET_ID,
        "rule_set_version": 1,
        "profile_snapshot_id": PROFILE_SNAPSHOT_ID,
        "eligibility_result": result_values(),
        "compiler_version": "phase4-compiler-v1",
        "engine_version": "phase4-engine-v1",
        "major_catalog_version": "phase4-synthetic-major-catalog-v1",
        "major_mapping_version": "phase4-synthetic-major-mapping-v1",
        "scenario_clock": date(2026, 8, 22),
        "input_sha256": "2" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def evaluation_run_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "run_id": RUN_ID,
        "dataset_id": "phase4-golden-synthetic",
        "dataset_version": "v1",
        "dataset_sha256": "3" * 64,
        "component": "ELIGIBILITY",
        "component_versions": {
            "contract": "0.4.0",
            "compiler": "phase4-compiler-v1",
            "engine": "phase4-engine-v1",
            "major_catalog": "phase4-synthetic-major-catalog-v1",
            "major_mapping": "phase4-synthetic-major-mapping-v1",
        },
        "synthetic": True,
        "status": "COMPLETED",
        "case_results": [
            {
                "case_id": "phase4-case-001",
                "expected_status": "ELIGIBLE",
                "actual_status": "ELIGIBLE",
                "passed": True,
                "match_snapshot_id": MATCH_SNAPSHOT_ID,
                "reason_codes": ["RULE_SATISFIED"],
            }
        ],
        "metrics": {
            "total_cases": 1,
            "passed_cases": 1,
            "unexpected_ineligible_count": 0,
            "replay_mismatch_count": 0,
            "status_counts": {
                "ELIGIBLE": 1,
                "LIKELY_ELIGIBLE": 0,
                "UNCERTAIN": 0,
                "INELIGIBLE": 0,
            },
        },
        "started_at": NOW,
        "completed_at": NOW,
        "error_summary": None,
    }
    values.update(changes)
    return values


def test_controlled_values_and_evidence_precedence_are_fixed() -> None:
    assert set(EligibilityStatus) == {
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.LIKELY_ELIGIBLE,
        EligibilityStatus.UNCERTAIN,
        EligibilityStatus.INELIGIBLE,
    }
    assert RuleEvidenceAuthority.LATEST_OFFICIAL_CORRECTION.precedence == 600
    assert RuleEvidenceAuthority.FORMAL_OFFICIAL_ATTACHMENT.precedence == 500
    assert RuleEvidenceAuthority.ORIGINAL_OFFICIAL_NOTICE.precedence == 400
    assert RuleEvidenceAuthority.OFFICIAL_FAQ_GUIDANCE.precedence == 300
    assert RuleEvidenceAuthority.HUMAN_APPROVED_MAPPING.precedence == 200
    assert RuleEvidenceAuthority.LLM_SEMANTIC_INFERENCE.precedence == 100
    assert EducationLevel.BACHELOR.value == "BACHELOR"
    assert RuleOperator.CONTAINS_ALL.value == "CONTAINS_ALL"


def test_rule_evidence_rejects_authority_precedence_mismatch() -> None:
    with pytest.raises(ValidationError, match="precedence"):
        RuleEvidenceSchemaV04.model_validate(
            evidence_values(authority="LLM_SEMANTIC_INFERENCE", precedence=300)
        )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"field": None}, "field"),
        ({"value_type": None}, "value_type"),
        ({"evidence": []}, "evidence"),
        ({"value": []}, "non-empty"),
        ({"value": ["MASTER", "BACHELOR"]}, "sorted"),
    ],
)
def test_atomic_rule_shape_is_strict(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RuleSchemaV04.model_validate(rule_values(**changes))


def test_composite_rule_shape_and_root_references_are_strict() -> None:
    composite = rule_values(
        operator="AND",
        field=None,
        value_type=None,
        value=None,
        operand_rule_ids=[RULE_ID],
        evidence=[],
    )
    with pytest.raises(ValidationError, match="at least two"):
        RuleSchemaV04.model_validate(composite)
    with pytest.raises(ValidationError, match="root"):
        RuleSetSchemaV04.model_validate(
            rule_set_values(root_rule_ids=[UUID("019b0000-0000-7000-8000-000000000199")])
        )


def test_profile_normalizes_unique_set_like_attributes() -> None:
    profile = ProfileSnapshotSchemaV04.model_validate(profile_values())
    assert profile.attributes.target_regions == ("Synthetic-Hangzhou", "Synthetic-Ningbo")
    assert profile.attributes.certificates == ("CET4",)
    with pytest.raises(ValidationError, match="duplicates"):
        ProfileSnapshotSchemaV04.model_validate(
            profile_values(
                attributes=profile_values()["attributes"]
                | {"certificates": ["CET4", "CET4"]}  # type: ignore[operator]
            )
        )


def test_eligibility_result_lists_must_match_rule_outcomes() -> None:
    with pytest.raises(ValidationError, match="outcome"):
        EligibilityResultSchemaV04.model_validate(result_values(satisfied_rule_ids=[]))
    with pytest.raises(ValidationError, match="official deterministic conflict"):
        EligibilityResultSchemaV04.model_validate(
            result_values(
                status="INELIGIBLE",
                rule_evaluations=[
                    rule_evaluation_values(
                        outcome="CONFLICT",
                        deterministic=False,
                        official_evidence=False,
                        evidence_ref_ids=[],
                    )
                ],
                satisfied_rule_ids=[],
                conflict_rule_ids=[RULE_ID],
            )
        )


def test_match_snapshot_requires_engine_consistency_and_nonempty_evaluations() -> None:
    with pytest.raises(ValidationError, match="engine_version"):
        MatchSnapshotSchemaV04.model_validate(match_values(engine_version="other-engine"))
    with pytest.raises(ValidationError):
        MatchSnapshotSchemaV04.model_validate(match_values(input_sha256="0" * 63))


def test_completed_evaluation_run_requires_matching_metrics() -> None:
    run = EvaluationRunSchemaV04.model_validate(evaluation_run_values())
    assert run.metrics is not None and run.metrics.passed_cases == 1
    with pytest.raises(ValidationError, match="metrics"):
        EvaluationRunSchemaV04.model_validate(
            evaluation_run_values(
                metrics=evaluation_run_values()["metrics"] | {"passed_cases": 0}  # type: ignore[operator]
            )
        )


def test_old_schema_bytes_remain_unchanged() -> None:
    for directory, rendered in (
        (V01_SCHEMA_DIRECTORY, render_phase1_schemas()),
        (V02_SCHEMA_DIRECTORY, render_phase2_schemas()),
        (V03_SCHEMA_DIRECTORY, render_phase3_schemas()),
    ):
        assert {path.name: path.read_bytes() for path in directory.glob("*.json")} == rendered


def test_v04_example_validates_with_pydantic_and_json_schema() -> None:
    from jsonschema import Draft202012Validator

    examples = json.loads(V04_EXAMPLE_PATH.read_text("utf-8"))
    assert set(examples) == {name.removesuffix(".schema.json") for name in PHASE4_SCHEMAS}
    for name, model in PHASE4_SCHEMAS.items():
        key = name.removesuffix(".schema.json")
        model.model_validate(examples[key])
        schema = json.loads((V04_SCHEMA_DIRECTORY / name).read_text("utf-8"))
        Draft202012Validator(schema).validate(examples[key])


def test_v04_renderer_matches_checked_in_schema_bytes() -> None:
    rendered = render_phase4_schemas()
    assert set(rendered) == set(PHASE4_SCHEMAS)
    assert set(rendered) == {path.name for path in V04_SCHEMA_DIRECTORY.glob("*.schema.json")}
    for name, content in rendered.items():
        assert (V04_SCHEMA_DIRECTORY / name).read_bytes() == content


def test_v04_export_writes_only_to_v04_directory(tmp_path: Path) -> None:
    written = write_phase4_schemas(tmp_path)
    expected = tmp_path / "contracts" / "schemas" / "v0.4.0"
    assert set(written) == set(PHASE4_SCHEMAS)
    assert {path.parent for path in written.values()} == {expected}
    assert not (tmp_path / "contracts" / "schemas" / "v0.3.0").exists()


def test_phase4_schema_values_are_models() -> None:
    assert all(issubclass(model, BaseModel) for model in PHASE4_SCHEMAS.values())
