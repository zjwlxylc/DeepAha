"""Private GROUP fact bridge; old investigation and V08 unit kind contracts stay frozen."""

from typing import Any, Literal

from pydantic import Field, JsonValue

from deepaha.contracts.common import EntityId, Instant, Sha256
from deepaha.investigations.group_contracts import GroupContract, GroupSourceRecord

GROUP_FACT_VERSION = "group-fact-bridge/1.0.0"


class PrepareGroupFacts(GroupContract):
    check_id: EntityId
    expected_source_hash: Sha256


class DecideGroupFact(GroupContract):
    expected_preparation_hash: Sha256
    candidate_id: EntityId
    decision: Literal["APPROVE", "REJECT", "UNKNOWN", "NEEDS_ADJUDICATION"]
    evidence_support: Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
    precedence_check: Literal["PASSED", "FAILED", "UNKNOWN"]
    reason: str = Field(min_length=1, max_length=2000)


class PromoteGroupFacts(GroupContract):
    expected_preparation_hash: Sha256
    supersedes_id: EntityId | None = None
    reason: str = Field(min_length=1, max_length=2000)


class GroupFactEvidence(GroupContract):
    reference: dict[str, Any]
    check_reference: dict[str, Any]
    binding: dict[str, Any] | None


class GroupFactRow(GroupContract):
    source_index: int = Field(ge=0)
    original: dict[str, Any]
    entity_id: str
    original_field: str
    original_status: str
    mapping_version: Literal["group-fact-bridge/1.0.0"]
    target_scope: Literal["UNIT"]
    field_name: str | None
    raw_value: str | None
    normalized_value_candidate: JsonValue | None
    confidence: None
    abstained: bool
    candidate_reason_code: str
    issue_codes: tuple[str, ...]
    ready_for_persistence: bool
    candidate_id: EntityId | None
    evidence: tuple[GroupFactEvidence, ...]


class GroupFactExcluded(GroupContract):
    source_index: int = Field(ge=0)
    entity_id: str
    source_hash: Sha256
    reason: Literal["DIFFERENT_ENTITY_SCOPE"]


class GroupFactResult(GroupContract):
    contract_version: Literal["group-fact-bridge/1.0.0"]
    scope: Literal["GROUP_FACT_REVIEW_ONLY"]
    group_source: GroupSourceRecord
    check_id: EntityId
    check_hash: Sha256
    source_row_count: int = Field(ge=0)
    rows: tuple[GroupFactRow, ...]
    excluded_rows: tuple[GroupFactExcluded, ...]
    extraction_run_id: EntityId | None


class GroupFactRecord(GroupContract):
    preparation_id: EntityId
    result: GroupFactResult
    result_hash: Sha256
    reviewer_id: EntityId
    created_at: Instant
    decisions: dict[str, dict[str, Any]]
    history: tuple[dict[str, Any], ...]
    fact_set: dict[str, Any] | None
