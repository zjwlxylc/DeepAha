"""Private read-only preview; neither a persisted rule nor an applicability decision."""

from typing import Literal

from pydantic import Field, JsonValue

from deepaha.contracts.common import EntityId, Sha256
from deepaha.contracts.phase9b import ProposedRulePayloadSchemaV08
from deepaha.investigations.group_contracts import GroupContract, GroupIdentity
from deepaha.investigations.group_fact_contracts import GroupFactRecord

GROUP_RULE_PREVIEW_VERSION = "group-rule-preview/1.0.0"


class GroupRulePreviewRow(GroupContract):
    source_index: int = Field(ge=0)
    candidate_id: EntityId | None
    verified_fact_id: EntityId | None
    fact_state: Literal["KNOWN", "UNKNOWN"] | None
    normalized_value: JsonValue | None
    proposed_rule_payload: ProposedRulePayloadSchemaV08 | None
    evidence_ref_ids: tuple[EntityId, ...]
    reason_code: Literal[
        "GROUP_FIELD_UNPROCESSED",
        "FACT_REJECTED",
        "FACT_SET_NOT_SAVED",
        "FACT_UNKNOWN",
        "FIELD_NOT_EXECUTABLE",
        "INDEPENDENT_RULE_REVIEW_REQUIRED",
    ]


class GroupRulePreviewResult(GroupContract):
    contract_version: Literal["group-rule-preview/1.0.0"]
    derivation_version: str
    scope: Literal["READ_ONLY_GROUP_RULE_PREVIEW"]
    target: GroupIdentity
    fact_review: GroupFactRecord
    rows: tuple[GroupRulePreviewRow, ...]


class GroupRulePreview(GroupContract):
    result: GroupRulePreviewResult
    result_hash: Sha256
