"""Deterministic review-only composition; offline replay does not authenticate inputs."""

from copy import deepcopy
from typing import Any, Literal, Self

from pydantic import model_validator

from deepaha.contracts.common import Sha256
from deepaha.investigations.announcement_sources import _assemble as announcement_projection
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_contracts import GroupContract
from deepaha.investigations.group_inheritance_contracts import GroupInheritancePreview
from deepaha.investigations.rules import RULE_BRIDGE_VERSION
from deepaha.investigations.unit_snapshots import ADAPTER_VERSION
from deepaha.local_human_test.review import RULE_DERIVATION_VERSION
from deepaha.unit_qualification.contracts import CoverageCondition, UnitIdentity

CROSS_LEVEL_VERSION = "cross-level-condition-review/1.0.0"
Version = Literal["cross-level-condition-review/1.0.0"]


class CrossLevelDependencies(GroupContract):
    contract_version: Version
    # Retain the older adapter's exact record representation, including timestamp spelling.
    announcement: dict[str, Any]
    group: GroupInheritancePreview


class CrossLevelCondition(GroupContract):
    condition: CoverageCondition
    disposition: Literal["LOCAL", "INHERITED", "EXCLUDED", "UNRESOLVED"]
    source_pointer: str


class SemanticReviewGroup(GroupContract):
    field_name: str
    condition_ids: tuple[str, ...]
    excluded_condition_ids: tuple[str, ...]
    relation: Literal["NOT_EVALUATED"]


class CrossLevelSnapshot(GroupContract):
    contract_version: Version
    scope: Literal["CROSS_LEVEL_REVIEW_ONLY"]
    target: UnitIdentity
    base_v2_hash: Sha256
    conditions: tuple[CrossLevelCondition, ...]
    semantic_review_groups: tuple[SemanticReviewGroup, ...]
    blockers: tuple[str, ...]
    executable: Literal[False]
    overall_qualification: Literal["UNCERTAIN"]


class CrossLevelReview(GroupContract):
    dependencies: CrossLevelDependencies
    dependencies_hash: Sha256
    snapshot: CrossLevelSnapshot
    snapshot_hash: Sha256

    @model_validator(mode="after")
    def require_exact_projection(self) -> Self:
        expected = _compose_cross_level(
            self.dependencies.announcement,
            self.dependencies.group.model_dump(mode="json"),
        )
        if self.model_dump(mode="json") != expected:
            raise ValueError("cross-level review must equal the full deterministic projection")
        return self


def _compose_cross_level(announcement: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    """Compose complete trusted-adapter exports, not user-supplied approvals."""
    GroupInheritancePreview.model_validate(group)
    preview = group["dependencies"]["group_source"]["rule_preview"]
    if preview is not None and preview["result"]["derivation_version"] != RULE_DERIVATION_VERSION:
        raise ValueError("unsupported group rule derivation")
    base = group["snapshot"]["base_v2"]
    try:
        if base["context"]["adapter_version"] != ADAPTER_VERSION:
            raise ValueError("unsupported base snapshot adapter")
        if announcement["snapshot"]["base_v2"] != base:
            raise ValueError("cross-level inputs must share the exact complete base")
        sources = announcement["dependencies"]["announcement_sources"]
        for source in sources:
            preparation = source["rule_preparation"]
            if preparation is not None and preparation["compiler_version"] != RULE_BRIDGE_VERSION:
                raise ValueError("unsupported announcement rule compiler")
            if any(c["compiler_version"] != RULE_BRIDGE_VERSION for c in source["rule_candidates"]):
                raise ValueError("unsupported announcement candidate compiler")
        conditions = [
            c for c in base["plan"]["manifest"]["conditions"] if c["scope"] == "ANNOUNCEMENT"
        ]
        represented = [
            (source["entity_id"], row["entity_id"], row["source_index"], digest(row))
            for source in sources
            for row in source["source_rows"]
        ]
        if sorted(represented) != sorted(
            (c["source_entity_id"], c["source_entity_id"], c["source_index"], c["source_sha256"])
            for c in conditions
        ):
            raise ValueError("announcement source rows must match the frozen full denominator")
        expected = announcement_projection(base, sources)
        if expected != announcement:
            raise ValueError("announcement input must equal the full source projection")
    except (KeyError, TypeError, IndexError, InvestigationError) as exc:
        raise ValueError("invalid announcement source projection") from exc

    rows: list[dict[str, Any]] = []
    parent_rows = {
        "ANNOUNCEMENT": ("announcement", "announcement_conditions", announcement),
        "EMPLOYER_GROUP": ("group", "group_conditions", group),
    }
    # Iterate the manifest, never a client-selected list of applicable rules.
    for index, condition in enumerate(base["plan"]["manifest"]["conditions"]):
        disposition = "LOCAL"
        pointer = f"/dependencies/group/snapshot/base_v2/plan/manifest/conditions/{index}"
        if condition["scope"] != "UNIT":
            name, key, source = parent_rows[condition["scope"]]
            matches = [
                (i, r) for i, r in enumerate(source["snapshot"][key]) if r["condition"] == condition
            ]
            if len(matches) != 1:
                raise ValueError("cross-level source must represent every condition exactly once")
            i, row = matches[0]
            disposition = {"INHERIT": "INHERITED", "EXCLUDE": "EXCLUDED"}.get(
                row["disposition"], row["disposition"]
            )
            pointer = f"/dependencies/{name}/snapshot/{key}/{i}"
        rows.append(
            {
                "condition": deepcopy(condition),
                "disposition": disposition,
                "source_pointer": pointer,
            }
        )
    by_field: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_field.setdefault(row["condition"]["field_name"], []).append(row)
    review_groups = [
        {
            "field_name": field,
            "condition_ids": [r["condition"]["condition_id"] for r in members],
            "excluded_condition_ids": [
                r["condition"]["condition_id"] for r in members if r["disposition"] == "EXCLUDED"
            ],
            "relation": "NOT_EVALUATED",
        }
        for field, members in sorted(by_field.items())
        if len({r["condition"]["scope"] for r in members}) > 1
    ]
    dependencies = {
        "contract_version": CROSS_LEVEL_VERSION,
        "announcement": deepcopy(announcement),
        "group": deepcopy(group),
    }
    snapshot = {
        "contract_version": CROSS_LEVEL_VERSION,
        "scope": "CROSS_LEVEL_REVIEW_ONLY",
        "target": deepcopy(base["plan"]["target"]),
        "base_v2_hash": digest(base),
        "conditions": rows,
        "semantic_review_groups": review_groups,
        "blockers": sorted(
            set(base["plan"]["manifest"]["upstream_blockers"])
            | {"CROSS_LEVEL_SEMANTICS_NOT_REVIEWED"}
        ),
        "executable": False,
        "overall_qualification": "UNCERTAIN",
    }
    return {
        "dependencies": dependencies,
        "dependencies_hash": digest(dependencies),
        "snapshot": snapshot,
        "snapshot_hash": digest(snapshot),
    }


def replay_cross_level(value: dict[str, Any], *, expected_dependencies_hash: str) -> dict[str, Any]:
    """Replay against an independently retained digest of a trusted online export.

    The caller must not take expected_dependencies_hash from the untrusted package.
    This authenticates neither humans nor current state; online use must rebuild from DB.
    The legacy announcement projection is not an offline approval-record validator.
    """
    if digest(value.get("dependencies")) != expected_dependencies_hash:
        raise ValueError("cross-level dependencies differ from the trusted export digest")
    return CrossLevelReview.model_validate(value).model_dump(mode="json")
