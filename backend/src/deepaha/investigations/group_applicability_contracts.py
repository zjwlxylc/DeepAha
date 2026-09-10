"""Exact identities for read-only GROUP applicability preparation."""

from typing import Literal

from deepaha.contracts.common import EntityId, NonEmptyString, Sha256
from deepaha.investigations.group_contracts import GroupContract, GroupIdentity, GroupMember
from deepaha.unit_qualification.contracts import UnitIdentity


class GroupApplicabilityContext(GroupContract):
    contract_version: Literal["group-rule-applicability-context/1.0.0"]
    task_id: EntityId
    target_plan_id: EntityId
    target_plan_hash: Sha256
    target_plan_context_hash: Sha256
    target: UnitIdentity
    target_entity_id: NonEmptyString
    source_group: GroupIdentity
    group_binding_id: EntityId
    group_source_hash: Sha256
    member: GroupMember
    binding_id: EntityId
    check_id: EntityId
    source_bundle_revision_id: EntityId
    source_rule_preparation_id: EntityId
    source_rule_preparation_hash: Sha256
    source_rule_candidate_id: EntityId
    source_rule_approval_id: EntityId
    source_rule_approval_hash: Sha256
    source_review_hash: Sha256
