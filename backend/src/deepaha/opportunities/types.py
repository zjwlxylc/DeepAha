from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import (
    ApplicationWindowSchema,
    OpportunityDocumentRole,
    ResolutionDisposition,
)


class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True, slots=True)
class OpportunityPatch:
    canonical_title: str | _Unset = UNSET
    type: OpportunityTypeV02 | _Unset = UNSET
    issuer_name: str | _Unset = UNSET
    jurisdiction: str | None | _Unset = UNSET
    status: OpportunityStatus | _Unset = UNSET
    published_at: datetime | None | _Unset = UNSET
    application_window: ApplicationWindowSchema | _Unset = UNSET
    application_url: str | None | _Unset = UNSET
    attachment_urls: tuple[str, ...] | _Unset = UNSET
    locations: tuple[str, ...] | _Unset = UNSET


@dataclass(frozen=True, slots=True)
class ResolutionDocument:
    document_id: UUID
    source_id: UUID
    source_tier: SourceTier
    evidence_ref_id: UUID
    role: OpportunityDocumentRole
    canonical_url: str | None
    external_id: str | None
    references_document_ids: tuple[UUID, ...]
    effective_at: datetime
    facts: OpportunityPatch

    def __post_init__(self) -> None:
        references = tuple(sorted(set(self.references_document_ids), key=lambda value: value.int))
        object.__setattr__(self, "references_document_ids", references)
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at must include timezone information")


@dataclass(frozen=True, slots=True)
class ResolutionTarget:
    opportunity_id: UUID
    public_id: str
    primary_identity_key: str


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    disposition: ResolutionDisposition
    opportunity_id: UUID | None
    public_id: str | None
    candidate_opportunity_ids: tuple[UUID, ...]
    reason_codes: tuple[str, ...]
    resolution_key: str

    def __post_init__(self) -> None:
        candidates = tuple(sorted(set(self.candidate_opportunity_ids), key=lambda value: value.int))
        object.__setattr__(self, "candidate_opportunity_ids", candidates)


def _freeze_target_map(
    values: Mapping[str, tuple[ResolutionTarget, ...]],
) -> Mapping[str, tuple[ResolutionTarget, ...]]:
    copied = {
        key: tuple(sorted(set(targets), key=lambda target: target.opportunity_id.int))
        for key, targets in values.items()
    }
    return MappingProxyType(dict(sorted(copied.items())))


@dataclass(frozen=True, slots=True)
class ResolutionIndex:
    document_links: Mapping[UUID, ResolutionTarget] = field(default_factory=dict)
    external_keys: Mapping[str, tuple[ResolutionTarget, ...]] = field(default_factory=dict)
    url_keys: Mapping[str, tuple[ResolutionTarget, ...]] = field(default_factory=dict)
    weak_candidates: Mapping[str, tuple[ResolutionTarget, ...]] = field(default_factory=dict)
    public_ids: Mapping[str, tuple[ResolutionTarget, ...]] = field(default_factory=dict)
    decisions_by_document: Mapping[UUID, ResolutionDecision] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "document_links",
            MappingProxyType(
                dict(sorted(self.document_links.items(), key=lambda item: item[0].int))
            ),
        )
        for name in ("external_keys", "url_keys", "weak_candidates", "public_ids"):
            object.__setattr__(self, name, _freeze_target_map(getattr(self, name)))
        object.__setattr__(
            self,
            "decisions_by_document",
            MappingProxyType(
                dict(sorted(self.decisions_by_document.items(), key=lambda item: item[0].int))
            ),
        )

    @classmethod
    def empty(cls) -> ResolutionIndex:
        return cls()


__all__ = [
    "UNSET",
    "OpportunityPatch",
    "ResolutionDecision",
    "ResolutionDocument",
    "ResolutionIndex",
    "ResolutionTarget",
]
