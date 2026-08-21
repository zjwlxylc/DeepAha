import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from deepaha.contracts.export import (
    PHASE3_SCHEMAS,
    render_phase1_schemas,
    render_phase2_schemas,
    render_phase3_schemas,
    write_phase3_schemas,
)
from deepaha.contracts.phase3 import (
    ApplicationWindowSchema,
    DocumentOpportunityLinkSchema,
    OpportunityAliasSchemaV03,
    OpportunityEventSchemaV03,
    OpportunityFieldChangeSchema,
    OpportunityIdentityActionSchema,
    OpportunityResolutionCandidateSchema,
    OpportunitySnapshotSchema,
    OpportunityVersionSchemaV03,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
V01_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.1.0"
V02_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.2.0"
V03_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.3.0"
V03_EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.3.0" / "phase-3-example.json"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
OPPORTUNITY_ID = UUID("019b0000-0000-7000-8000-000000000010")
DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000000011")
EVIDENCE_REF_ID = UUID("019b0000-0000-7000-8000-000000000012")


def snapshot_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "canonical_title": "Synthetic youth opportunity",
        "type": "YOUTH_DEVELOPMENT_PROGRAM",
        "issuer_name": "Synthetic Example Authority",
        "jurisdiction": None,
        "status": "OPEN",
        "published_at": NOW,
        "application_window": {
            "opens_on": date(2026, 8, 22),
            "closes_on": date(2026, 9, 22),
            "timezone": "Asia/Shanghai",
        },
        "application_url": "https://example.gov/apply",
        "attachment_urls": [
            "https://example.gov/files/notice.pdf",
            "https://example.gov/files/positions.xlsx",
        ],
        "locations": ["Hangzhou", "Ningbo"],
    }
    values.update(changes)
    return values


def change_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "field_path": "canonical_title",
        "before": None,
        "after": "Synthetic youth opportunity",
        "evidence_ref_id": EVIDENCE_REF_ID,
    }
    values.update(changes)
    return values


def field_evidence_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "field_path": "canonical_title",
        "precedence": 600,
        "evidence_ref_id": EVIDENCE_REF_ID,
        "effective_at": NOW,
    }
    values.update(changes)
    return values


def version_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "opportunity_id": OPPORTUNITY_ID,
        "version": 1,
        "effective_from": NOW,
        "source_document_id": DOCUMENT_ID,
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "snapshot": snapshot_values(),
        "field_evidence": [field_evidence_values()],
        "changes": [change_values()],
        "content_sha256": "1" * 64,
        "review_status": "NOT_REQUIRED",
        "created_at": NOW,
    }
    values.update(changes)
    return values


def event_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "event_id": UUID("019b0000-0000-7000-8000-000000000013"),
        "opportunity_id": OPPORTUNITY_ID,
        "from_version": None,
        "to_version": 1,
        "event_type": "CREATED",
        "changed_fields": ["canonical_title"],
        "changes": [change_values()],
        "source_document_id": DOCUMENT_ID,
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "detected_at": NOW,
    }
    values.update(changes)
    return values


def member_values(
    role: str,
    opportunity_id: UUID = OPPORTUNITY_ID,
) -> dict[str, object]:
    return {"opportunity_id": opportunity_id, "role": role}


def identity_action_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "action_id": UUID("019b0000-0000-7000-8000-000000000014"),
        "action_type": "MERGE",
        "members": [
            member_values("SOURCE", UUID("019b0000-0000-7000-8000-000000000015")),
            member_values("TARGET"),
        ],
        "reversal_of_action_id": None,
        "actor": "phase3-synthetic-test",
        "reason": "Synthetic duplicate correction",
        "source_document_id": DOCUMENT_ID,
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "occurred_at": NOW,
    }
    values.update(changes)
    return values


def test_snapshot_rejects_duplicate_urls_and_locations() -> None:
    for changes in (
        {"attachment_urls": ["https://example.gov/a", "https://example.gov/a"]},
        {"locations": ["Hangzhou", "Hangzhou"]},
    ):
        with pytest.raises(ValidationError, match="duplicate"):
            OpportunitySnapshotSchema.model_validate(snapshot_values(**changes))


def test_application_window_rejects_reverse_dates_and_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="closes_on"):
        ApplicationWindowSchema(
            opens_on=date(2026, 9, 1),
            closes_on=date(2026, 8, 31),
            timezone="Asia/Shanghai",
        )
    with pytest.raises(ValidationError, match="timezone"):
        ApplicationWindowSchema(
            opens_on=None,
            closes_on=None,
            timezone="Mars/Olympus",
        )


def test_field_change_rejects_equal_before_and_after() -> None:
    with pytest.raises(ValidationError, match="differ"):
        OpportunityFieldChangeSchema.model_validate(change_values(before="same", after="same"))


def test_version_requires_nonempty_changes_and_matching_evidence() -> None:
    with pytest.raises(ValidationError):
        OpportunityVersionSchemaV03.model_validate(version_values(changes=[]))
    with pytest.raises(ValidationError, match="evidence"):
        OpportunityVersionSchemaV03.model_validate(
            version_values(
                field_evidence=[
                    field_evidence_values(
                        evidence_ref_id=UUID("019b0000-0000-7000-8000-000000000099")
                    )
                ]
            )
        )


def test_created_event_requires_null_from_version_and_to_version_one() -> None:
    with pytest.raises(ValidationError, match="CREATED"):
        OpportunityEventSchemaV03.model_validate(event_values(from_version=1, to_version=2))


def test_noncreated_event_requires_next_version() -> None:
    with pytest.raises(ValidationError, match="continuous"):
        OpportunityEventSchemaV03.model_validate(
            event_values(event_type="UPDATED", from_version=1, to_version=3)
        )


def test_event_changed_fields_must_match_changes_order() -> None:
    with pytest.raises(ValidationError, match="match"):
        OpportunityEventSchemaV03.model_validate(event_values(changed_fields=["status"]))


def test_link_end_fields_are_both_present_or_both_absent() -> None:
    values = {
        "link_id": UUID("019b0000-0000-7000-8000-000000000016"),
        "document_id": DOCUMENT_ID,
        "opportunity_id": OPPORTUNITY_ID,
        "role": "ATTACHMENT",
        "resolution_key": "document:synthetic-primary",
        "resolver_version": "0.3.0",
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "linked_at": NOW,
        "ended_at": NOW,
        "ended_by_identity_action_id": None,
    }
    with pytest.raises(ValidationError, match="both"):
        DocumentOpportunityLinkSchema.model_validate(values)


def test_candidate_starts_pending_and_rejects_extra_fields() -> None:
    values = {
        "candidate_id": UUID("019b0000-0000-7000-8000-000000000017"),
        "document_id": DOCUMENT_ID,
        "candidate_opportunity_ids": [OPPORTUNITY_ID],
        "proposed_role": "CORRECTION",
        "proposed_snapshot": snapshot_values(),
        "reason_codes": ["STRONG_KEY_CONFLICT"],
        "resolver_version": "0.3.0",
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "review_status": "APPROVED",
        "created_at": NOW,
    }
    with pytest.raises(ValidationError, match="PENDING"):
        OpportunityResolutionCandidateSchema.model_validate(values)
    values["review_status"] = "PENDING"
    values["cookie"] = "secret"
    with pytest.raises(ValidationError, match="Extra inputs"):
        OpportunityResolutionCandidateSchema.model_validate(values)


def test_candidate_rejects_duplicate_ids_and_reason_codes() -> None:
    base = {
        "candidate_id": UUID("019b0000-0000-7000-8000-000000000017"),
        "document_id": DOCUMENT_ID,
        "candidate_opportunity_ids": [OPPORTUNITY_ID],
        "proposed_role": "CORRECTION",
        "proposed_snapshot": None,
        "reason_codes": ["STRONG_KEY_CONFLICT"],
        "resolver_version": "0.3.0",
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "review_status": "PENDING",
        "created_at": NOW,
    }
    for changes in (
        {"candidate_opportunity_ids": [OPPORTUNITY_ID, OPPORTUNITY_ID]},
        {"reason_codes": ["STRONG_KEY_CONFLICT", "STRONG_KEY_CONFLICT"]},
    ):
        with pytest.raises(ValidationError, match="unique"):
            OpportunityResolutionCandidateSchema.model_validate(base | changes)


def test_alias_requires_source_for_external_id() -> None:
    values = {
        "alias_id": UUID("019b0000-0000-7000-8000-000000000018"),
        "opportunity_id": OPPORTUNITY_ID,
        "alias_type": "EXTERNAL_ID",
        "alias_value": "DeepAha-2026-001",
        "normalized_value": "deepaha-2026-001",
        "source_id": None,
        "source_document_id": DOCUMENT_ID,
        "source_evidence_ref_id": EVIDENCE_REF_ID,
        "created_at": NOW,
    }
    with pytest.raises(ValidationError, match="source_id"):
        OpportunityAliasSchemaV03.model_validate(values)


def test_identity_merge_requires_one_target_and_at_least_one_source() -> None:
    with pytest.raises(ValidationError, match="TARGET"):
        OpportunityIdentityActionSchema.model_validate(
            identity_action_values(members=[member_values("SOURCE")])
        )


def test_reversal_requires_reversal_of_and_copied_members_shape() -> None:
    with pytest.raises(ValidationError, match="reversal_of"):
        OpportunityIdentityActionSchema.model_validate(
            identity_action_values(action_type="MERGE_REVERSAL")
        )
    reversal = identity_action_values(
        action_type="MERGE_REVERSAL",
        reversal_of_action_id=UUID("019b0000-0000-7000-8000-000000000019"),
    )
    assert OpportunityIdentityActionSchema.model_validate(reversal).members


def test_nonreversal_forbids_reversal_of() -> None:
    with pytest.raises(ValidationError, match="forbids"):
        OpportunityIdentityActionSchema.model_validate(
            identity_action_values(
                reversal_of_action_id=UUID("019b0000-0000-7000-8000-000000000019")
            )
        )


def test_action_evidence_fields_are_paired() -> None:
    with pytest.raises(ValidationError, match="both"):
        OpportunityIdentityActionSchema.model_validate(
            identity_action_values(source_evidence_ref_id=None)
        )


def test_old_schema_bytes_remain_unchanged() -> None:
    for directory, rendered in (
        (V01_SCHEMA_DIRECTORY, render_phase1_schemas()),
        (V02_SCHEMA_DIRECTORY, render_phase2_schemas()),
    ):
        assert {path.name: path.read_bytes() for path in directory.glob("*.json")} == rendered


def test_v03_example_validates_with_pydantic_and_json_schema() -> None:
    from jsonschema import Draft202012Validator

    examples = json.loads(V03_EXAMPLE_PATH.read_text("utf-8"))
    assert set(examples) == {name.removesuffix(".schema.json") for name in PHASE3_SCHEMAS}
    for name, model in PHASE3_SCHEMAS.items():
        key = name.removesuffix(".schema.json")
        model.model_validate(examples[key])
        Draft202012Validator(json.loads((V03_SCHEMA_DIRECTORY / name).read_text("utf-8"))).validate(
            examples[key]
        )


def test_v03_renderer_matches_checked_in_schema_bytes() -> None:
    rendered = render_phase3_schemas()
    assert set(rendered) == set(PHASE3_SCHEMAS)
    assert set(rendered) == {path.name for path in V03_SCHEMA_DIRECTORY.glob("*.schema.json")}
    for name, content in rendered.items():
        assert (V03_SCHEMA_DIRECTORY / name).read_bytes() == content


def test_v03_export_writes_only_to_v03_directory(tmp_path: Path) -> None:
    written = write_phase3_schemas(tmp_path)
    expected = tmp_path / "contracts" / "schemas" / "v0.3.0"
    assert set(written) == set(PHASE3_SCHEMAS)
    assert {path.parent for path in written.values()} == {expected}
    assert not (tmp_path / "contracts" / "schemas" / "v0.1.0").exists()
    assert not (tmp_path / "contracts" / "schemas" / "v0.2.0").exists()


def test_phase3_schema_values_are_models() -> None:
    assert all(issubclass(model, BaseModel) for model in PHASE3_SCHEMAS.values())
