"""Private group identity contracts; the frozen V08 Unit contract is unchanged."""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256, VersionNumber
from deepaha.investigations.contracts import InvestigationPositionBinding


class GroupContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RegisterGroupSource(GroupContract):
    entity_id: str = Field(min_length=1, max_length=256)
    expected_source_hash: Sha256


class GroupMember(GroupContract):
    entity_id: NonEmptyString
    state: Literal["BOUND", "UNPROCESSED"]
    position_binding: InvestigationPositionBinding | None

    @model_validator(mode="after")
    def require_binding_shape(self) -> Self:
        if (self.state == "BOUND") != (self.position_binding is not None):
            raise ValueError("member state must preserve missing identity")
        if self.position_binding and self.position_binding.entity_id != self.entity_id:
            raise ValueError("member identity must match source child")
        return self


class GroupSourceContext(GroupContract):
    contract_version: Literal["group-identity/1.0.0"]
    scope: Literal["GROUP_SOURCE_ASSOCIATION_ONLY"]
    task_id: EntityId
    delivery_hash: Sha256
    binding_id: EntityId
    binding_hash: Sha256
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    source_bundle_revision_id: EntityId
    canonical_bundle_hash: Sha256
    source_snapshot_hash: Sha256
    source_group: dict[str, Any]
    source_entity: dict[str, Any]
    members: tuple[GroupMember, ...]
    membership_status: Literal["NO_MEMBERS", "UNPROCESSED_MEMBERS", "ALL_MEMBERS_BOUND"]

    @model_validator(mode="after")
    def require_full_source_denominator(self) -> Self:
        ids = [member.entity_id for member in self.members]
        if ids != [row["id"] for row in self.source_group.get("positions", [])] or len(
            set(ids)
        ) != len(ids):
            raise ValueError("members must preserve the full ordered source denominator")
        if self.source_entity.get("kind") != "unit" or self.source_entity.get(
            "id"
        ) != self.source_group.get("id"):
            raise ValueError("source group identity differs")
        expected = (
            "NO_MEMBERS"
            if not self.members
            else (
                "UNPROCESSED_MEMBERS"
                if any(m.state == "UNPROCESSED" for m in self.members)
                else "ALL_MEMBERS_BOUND"
            )
        )
        if self.membership_status != expected:
            raise ValueError("membership status differs from actual members")
        return self


class GroupIdentity(GroupContract):
    unit_kind: Literal["GROUP"]
    unit_id: EntityId
    public_id: str = Field(pattern=r"^unit_[0-9a-f]{32}$")
    unit_version_id: EntityId
    version: VersionNumber
    key: NonEmptyString
    label: NonEmptyString


class GroupSourceRecord(GroupContract):
    contract_version: Literal["group-identity/1.0.0"]
    scope: Literal["GROUP_SOURCE_ASSOCIATION_ONLY"]
    group_binding_id: EntityId
    group_identity: GroupIdentity
    source: GroupSourceContext
    source_hash: Sha256
    reviewer_id: EntityId
    created_at: Instant


class GroupSourcePreview(GroupContract):
    source: GroupSourceContext
    source_hash: Sha256
    existing_group_id: EntityId | None
    registration: GroupSourceRecord | None
