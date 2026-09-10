"""Review-only relationship records. Structural validity is not human authentication.

The online adapter must rebuild sources and bound evidence from authorized DB rows.
No producer/reviewer identity or evidence supplied by a client is trusted here.
"""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from deepaha.contracts.common import EntityId, Instant, Sha256, normalize_instant
from deepaha.investigations.contracts import digest
from deepaha.investigations.cross_level_review import CrossLevelReview
from deepaha.investigations.group_applicability_decision_contracts import (
    GroupApplicabilityBoundEvidence,
)
from deepaha.investigations.group_contracts import GroupContract

ADJUDICATION_VERSION = "cross-level-adjudication/1.0.0"


class BoundRelationEvidence(GroupApplicabilityBoundEvidence):
    purpose: Literal["CONDITION", "RELATION"]
    condition_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_literal_evidence(self) -> Self:
        if (
            not self.quote.strip()
            or not self.locator
            or not self.material_id.strip()
            or not self.source_url.strip()
            or len(set(self.condition_ids)) != len(self.condition_ids)
            or any(not item.strip() for item in self.condition_ids)
        ):
            raise ValueError("relation evidence requires exact unique conditions and location")
        return self


class RelationProposal(GroupContract):
    contract_version: Literal["cross-level-adjudication/1.0.0"]
    scope: Literal["CROSS_LEVEL_ADJUDICATION_REVIEW_ONLY"]
    proposal_id: EntityId
    producer_id: EntityId
    created_at: Instant
    source_review: CrossLevelReview
    source_review_hash: Sha256
    condition_ids: tuple[str, ...] = Field(min_length=2)
    relation: Literal["CUMULATIVE", "EXCEPTION", "CONFLICT", "UNRESOLVED"]
    displaced_condition_ids: tuple[str, ...]
    reason: str = Field(min_length=1, max_length=2000)
    evidence: tuple[BoundRelationEvidence, ...] = Field(max_length=200)

    @model_validator(mode="after")
    def require_exact_relation(self) -> Self:
        if self.source_review_hash != digest(self.source_review.model_dump(mode="json")):
            raise ValueError("proposal source hash differs from complete source review")
        rows = self.source_review.snapshot.conditions
        selected = [r for r in rows if r.condition.condition_id in self.condition_ids]
        if tuple(r.condition.condition_id for r in selected) != self.condition_ids:
            raise ValueError("selected conditions must be unique and in full manifest order")
        if len({r.condition.scope for r in selected}) < 2:
            raise ValueError("relation must bind conditions from at least two scopes")
        if not self.reason.strip():
            raise ValueError("relation reason must not be blank")
        if self.relation != "UNRESOLVED" and any(
            r.disposition not in {"LOCAL", "INHERITED"}
            or (r.disposition == "LOCAL" and r.condition.state != "KNOWN")
            for r in selected
        ):
            raise ValueError("resolved relation cannot revive inactive or unknown conditions")
        displaced = self.displaced_condition_ids
        if self.relation == "EXCEPTION":
            if (
                not displaced
                or len(displaced) >= len(self.condition_ids)
                or tuple(c for c in self.condition_ids if c in displaced) != displaced
            ):
                raise ValueError("displaced conditions must be an ordered nonempty proper subset")
        elif displaced:
            raise ValueError("only an explicit exception may name displaced conditions")
        evidence_keys = []
        covered: set[str] = set()
        has_relation = False
        for item in self.evidence:
            if (
                tuple(c for c in self.condition_ids if c in item.condition_ids)
                != item.condition_ids
            ):
                raise ValueError("evidence binds conditions outside the exact selected relation")
            evidence_keys.append(
                (item.purpose, item.member_id, item.block_id, item.quote, item.condition_ids)
            )
            if item.purpose == "RELATION":
                if item.condition_ids != self.condition_ids:
                    raise ValueError("relation evidence must bind the full selected relationship")
                has_relation = True
            else:
                covered.update(item.condition_ids)
        if len(set(evidence_keys)) != len(evidence_keys):
            raise ValueError("duplicate relationship evidence")
        if self.relation != "UNRESOLVED" and (
            covered != set(self.condition_ids) or not has_relation
        ):
            raise ValueError(
                "resolved relation needs every condition and explicit relation evidence"
            )
        return self


class RelationDecision(GroupContract):
    decision_id: EntityId
    proposal_id: EntityId
    proposal_hash: Sha256
    sequence: int = Field(ge=1, strict=True)
    previous_decision_id: EntityId | None
    reviewer_id: EntityId
    created_at: Instant
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    reason: str = Field(min_length=1, max_length=2000)


class AdjudicationPackage(GroupContract):
    proposal: RelationProposal
    decisions: tuple[RelationDecision, ...]

    @model_validator(mode="after")
    def require_independent_continuous_history(self) -> Self:
        proposal = self.proposal
        proposal_hash = digest(proposal.model_dump(mode="json"))
        previous = None
        ids = set()
        for sequence, row in enumerate(self.decisions, 1):
            if row.reviewer_id == proposal.producer_id:
                raise ValueError("relationship review must be independent of its producer")
            if row.decision == "APPROVE" and proposal.relation == "UNRESOLVED":
                raise ValueError("an unresolved interpretation cannot be approved")
            if (
                row.proposal_id != proposal.proposal_id
                or row.proposal_hash != proposal_hash
                or row.sequence != sequence
                or row.previous_decision_id != (previous.decision_id if previous else None)
                or row.decision_id in ids
                or row.created_at < (previous.created_at if previous else proposal.created_at)
                or not row.reason.strip()
            ):
                raise ValueError(
                    "relationship history differs from immutable proposal or predecessor"
                )
            ids.add(row.decision_id)
            previous = row
        return self


def _target_key(review: CrossLevelReview) -> tuple[str, str]:
    group = review.dependencies.group
    return (
        str(group.dependencies.group_source.source.task_id),
        str(group.snapshot.base_v2.plan_id),
    )


def replay_adjudication(
    value: dict[str, Any],
    *,
    expected_package_hash: str,
    current_source_review: dict[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    """Replay against an independent full-history anchor and trusted current export.

    The caller must independently obtain both anchor and current source. This is
    not an authentication API, current DB check, evidence verifier or compiler.
    """
    now = normalize_instant(as_of)
    if digest(value) != expected_package_hash:
        raise ValueError("relationship history differs from trusted package digest")
    package = AdjudicationPackage.model_validate(value)
    current = CrossLevelReview.model_validate(current_source_review)
    proposal = package.proposal
    if _target_key(proposal.source_review) != _target_key(current):
        raise ValueError("current source review belongs to another task or plan")
    if proposal.created_at > now or any(d.created_at > now for d in package.decisions):
        raise ValueError("relationship records are in the future of the trusted replay clock")
    latest = package.decisions[-1] if package.decisions else None
    stale = proposal.source_review_hash != digest(current.model_dump(mode="json"))
    status = (
        "STALE"
        if stale
        else (
            {
                "APPROVE": "APPROVED",
                "REJECT": "REJECTED",
                "NEEDS_ADJUDICATION": "NEEDS_ADJUDICATION",
            }[latest.decision]
            if latest
            else "UNREVIEWED"
        )
    )
    snapshot = proposal.source_review.snapshot.model_dump(mode="json")
    blockers = set(snapshot["blockers"]) | {"CROSS_LEVEL_ADJUDICATION_REVIEW_ONLY"}
    if stale:
        blockers.add("CROSS_LEVEL_ADJUDICATION_STALE")
    if proposal.relation == "CONFLICT" and status == "APPROVED":
        blockers.add("CROSS_LEVEL_CONFLICT_RECORDED")
    return {
        "contract_version": ADJUDICATION_VERSION,
        "scope": "CROSS_LEVEL_ADJUDICATION_REVIEW_ONLY",
        "proposal_id": str(proposal.proposal_id),
        "source_review_hash": proposal.source_review_hash,
        "current_source_review_hash": digest(current.model_dump(mode="json")),
        "source_snapshot": snapshot,
        "selected_condition_ids": list(proposal.condition_ids),
        "unselected_condition_ids": [
            row["condition"]["condition_id"]
            for row in snapshot["conditions"]
            if row["condition"]["condition_id"] not in proposal.condition_ids
        ],
        "relation": proposal.relation,
        "displaced_condition_ids": list(proposal.displaced_condition_ids),
        "status": status,
        "latest": latest.model_dump(mode="json") if latest else None,
        "blockers": sorted(blockers),
        "executable": False,
        "overall_qualification": "UNCERTAIN",
    }
