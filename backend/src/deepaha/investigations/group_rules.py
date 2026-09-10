"""Project exact group facts without writing candidates, rules or inheritance."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_facts import _check_materialization, _checked, _describe
from deepaha.investigations.group_rule_contracts import (
    GROUP_RULE_PREVIEW_VERSION,
    GroupRulePreview,
    GroupRulePreviewResult,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import (
    RULE_DERIVATION_VERSION,
    build_rule_payload,
    require_human_fact_reviewer,
)
from deepaha.p9b.models import VerifiedFact, VerifiedFactEvidence, VersionedVerifiedFactSet
from deepaha.review.auth import ReviewerPrincipal


def preview_group_rules(
    store: InvestigationStore, task_id: UUID, prep_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        return build_group_rule_preview(store, session, task_id, prep_id)


def build_group_rule_preview(
    store: InvestigationStore, session: Session, task_id: UUID, prep_id: UUID
) -> dict[str, Any]:
    # Recheck source, identity, original material, actual facts and decisions in
    # the same transaction. A previous preview is never used as authority.
    prep = _checked(store, session, task_id, prep_id)
    review = _describe(store, session, prep)
    facts: dict[str, VerifiedFact] = {}
    if review["fact_set"] is not None:
        set_id = UUID(review["fact_set"]["fact_set_id"])
        fact_set = session.scalar(
            select(VersionedVerifiedFactSet)
            .where(VersionedVerifiedFactSet.verified_fact_set_id == set_id)
            .with_for_update()
        )
        if fact_set is None or fact_set.status != "ACTIVE":
            raise InvestigationError("GROUP_RULE_FACT_SET_NOT_ACTIVE")
        facts = {
            str(fact.candidate_id): fact
            for fact in session.scalars(
                select(VerifiedFact).where(VerifiedFact.verified_fact_set_id == set_id)
            )
        }
    rows = []
    # Enumerate original GROUP rows, including rejected and unprocessed rows,
    # rather than using the smaller set of executable or approved facts.
    for source in prep.result["rows"]:
        fact = facts.get(source["candidate_id"])
        decision = review["decisions"].get(source["candidate_id"], {})
        payload = None
        evidence_ids = []
        if source["candidate_id"] is None:
            reason = "GROUP_FIELD_UNPROCESSED"
        elif decision.get("decision") == "REJECT":
            reason = "FACT_REJECTED"
        elif fact is None:
            if review["fact_set"] is not None:
                raise InvestigationError("GROUP_RULE_FACT_DENOMINATOR_INVALID")
            reason = "FACT_SET_NOT_SAVED"
        elif fact.fact_state != "KNOWN":
            reason = "FACT_UNKNOWN"
        else:
            payload = build_rule_payload(
                field_name=fact.field_name, normalized_value=fact.normalized_value
            )
            reason = "FIELD_NOT_EXECUTABLE"
            if payload is not None:
                payload = payload.model_copy(
                    update={"code": f"group-preview-{fact.verified_fact_id}"}
                )
                reason = "INDEPENDENT_RULE_REVIEW_REQUIRED"
        if fact is not None:
            evidence_ids = list(
                session.scalars(
                    select(VerifiedFactEvidence.evidence_ref_id)
                    .where(VerifiedFactEvidence.verified_fact_id == fact.verified_fact_id)
                    .order_by(VerifiedFactEvidence.evidence_ref_id)
                )
            )
        rows.append(
            {
                "source_index": source["source_index"],
                "candidate_id": source["candidate_id"],
                "verified_fact_id": fact.verified_fact_id if fact else None,
                "fact_state": fact.fact_state if fact else None,
                "normalized_value": fact.normalized_value if fact else None,
                "proposed_rule_payload": payload,
                "evidence_ref_ids": evidence_ids,
                "reason_code": reason,
            }
        )
    # READ COMMITTED allows evidence appended by another transaction to be
    # visible after _describe. Recheck after the last read; never return a
    # projection whose actual evidence differs from the frozen receipt.
    _check_materialization(
        store,
        session,
        prep_id,
        UUID(review["fact_set"]["fact_set_id"]) if review["fact_set"] else None,
    )
    result = GroupRulePreviewResult.model_validate(
        {
            "contract_version": GROUP_RULE_PREVIEW_VERSION,
            "derivation_version": RULE_DERIVATION_VERSION,
            "scope": "READ_ONLY_GROUP_RULE_PREVIEW",
            "target": prep.result["group_source"]["group_identity"],
            "fact_review": review,
            "rows": rows,
        }
    ).model_dump(mode="json")
    return GroupRulePreview.model_validate(
        {"result": result, "result_hash": digest(result)}
    ).model_dump(mode="json")
