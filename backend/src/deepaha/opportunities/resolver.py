from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import OpportunityDocumentRole, ResolutionDisposition
from deepaha.opportunities.identity import (
    normalize_identity_text,
    normalize_official_url,
    stable_public_id_for_key,
    weak_fingerprint,
)
from deepaha.opportunities.types import (
    ResolutionDecision,
    ResolutionDocument,
    ResolutionIndex,
    ResolutionTarget,
)


def _candidate(
    document: ResolutionDocument,
    *,
    candidates: tuple[ResolutionTarget, ...] = (),
    reason: str,
    resolution_key: str | None = None,
) -> ResolutionDecision:
    return ResolutionDecision(
        disposition=ResolutionDisposition.NEEDS_REVIEW,
        opportunity_id=None,
        public_id=None,
        candidate_opportunity_ids=tuple(item.opportunity_id for item in candidates),
        reason_codes=(reason,),
        resolution_key=resolution_key or f"document:{document.document_id}",
    )


def _external_key(document: ResolutionDocument) -> str | None:
    if document.external_id is None:
        return None
    normalized = normalize_identity_text(document.external_id)
    if not normalized:
        return None
    return f"external:{document.source_id}:{normalized}"


def _url_key(document: ResolutionDocument) -> str | None:
    if document.canonical_url is None:
        return None
    return f"url:{normalize_official_url(document.canonical_url)}"


def _required_primary_facts_are_present(document: ResolutionDocument) -> bool:
    facts = document.facts
    return (
        isinstance(facts.canonical_title, str)
        and bool(normalize_identity_text(facts.canonical_title))
        and isinstance(facts.type, OpportunityTypeV02)
        and isinstance(facts.issuer_name, str)
        and bool(normalize_identity_text(facts.issuer_name))
        and isinstance(facts.status, OpportunityStatus)
    )


def _unique_targets(targets: list[ResolutionTarget]) -> tuple[ResolutionTarget, ...]:
    by_id = {target.opportunity_id: target for target in targets}
    return tuple(sorted(by_id.values(), key=lambda target: target.opportunity_id.int))


def resolve_document(
    document: ResolutionDocument,
    index: ResolutionIndex,
) -> ResolutionDecision:
    previous = index.decisions_by_document.get(document.document_id)
    if previous is not None:
        return previous

    strong_matches: list[tuple[str, ResolutionTarget]] = []
    for referenced_document_id in document.references_document_ids:
        linked_target = index.document_links.get(referenced_document_id)
        if linked_target is not None:
            strong_matches.append((f"document:{referenced_document_id}", linked_target))

    external_key = _external_key(document)
    if external_key is not None:
        strong_matches.extend(
            (external_key, target) for target in index.external_keys.get(external_key, ())
        )

    try:
        url_key = _url_key(document)
    except ValueError:
        return _candidate(document, reason="INVALID_STRONG_KEY")
    if url_key is not None:
        strong_matches.extend((url_key, target) for target in index.url_keys.get(url_key, ()))

    matched_targets = _unique_targets([target for _, target in strong_matches])
    if len(matched_targets) > 1:
        return _candidate(
            document,
            candidates=matched_targets,
            reason="STRONG_KEY_CONFLICT",
            resolution_key=strong_matches[0][0],
        )

    if document.source_tier is not SourceTier.OFFICIAL_PRIMARY:
        reason = (
            "AGGREGATOR_REQUIRES_REVIEW"
            if document.source_tier is SourceTier.OFFICIAL_AGGREGATOR
            else "UNTRUSTED_SOURCE_TIER"
        )
        return _candidate(
            document,
            candidates=matched_targets,
            reason=reason,
            resolution_key=strong_matches[0][0] if strong_matches else None,
        )

    if matched_targets:
        matched = matched_targets[0]
        matching_keys = [
            key for key, target in strong_matches if target.opportunity_id == matched.opportunity_id
        ]
        return ResolutionDecision(
            disposition=ResolutionDisposition.LINKED,
            opportunity_id=matched.opportunity_id,
            public_id=matched.public_id,
            candidate_opportunity_ids=(),
            reason_codes=(),
            resolution_key=matching_keys[0],
        )

    if document.role is not OpportunityDocumentRole.PRIMARY_NOTICE:
        return _candidate(document, reason="MISSING_STRONG_RELATION")

    if not _required_primary_facts_are_present(document):
        return _candidate(document, reason="INCOMPLETE_PRIMARY_FACTS")

    primary_key = external_key or url_key
    if primary_key is None:
        return _candidate(document, reason="MISSING_STABLE_KEY")

    fingerprint = weak_fingerprint(document.facts)
    weak_candidates = () if fingerprint is None else index.weak_candidates.get(fingerprint, ())
    if weak_candidates:
        return _candidate(
            document,
            candidates=weak_candidates,
            reason="POSSIBLE_DUPLICATE",
            resolution_key=primary_key,
        )

    public_id = stable_public_id_for_key(primary_key)
    public_id_targets = index.public_ids.get(public_id, ())
    if public_id_targets:
        same_identity = tuple(
            target for target in public_id_targets if target.primary_identity_key == primary_key
        )
        if len(same_identity) == 1 and len(public_id_targets) == 1:
            matched = same_identity[0]
            return ResolutionDecision(
                disposition=ResolutionDisposition.LINKED,
                opportunity_id=matched.opportunity_id,
                public_id=matched.public_id,
                candidate_opportunity_ids=(),
                reason_codes=(),
                resolution_key=primary_key,
            )
        return _candidate(
            document,
            candidates=public_id_targets,
            reason="PUBLIC_ID_COLLISION",
            resolution_key=primary_key,
        )

    return ResolutionDecision(
        disposition=ResolutionDisposition.CREATED,
        opportunity_id=None,
        public_id=public_id,
        candidate_opportunity_ids=(),
        reason_codes=(),
        resolution_key=primary_key,
    )


__all__ = ["resolve_document"]
