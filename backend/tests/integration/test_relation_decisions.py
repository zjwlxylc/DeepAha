"""Synthetic independent reviewers exercising actual append-only DB records."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid7

import pytest
from alembic import command as migration_command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.group_applicability_decisions import (
    DecideGroupApplicability,
    save_group_applicability,
)
from deepaha.investigations.relation_decisions import DecideRelation, save_relation_decision
from deepaha.investigations.relation_proposals import load_relation_proposal, save_relation_proposal
from deepaha.review.auth import ReviewerPrincipal
from deepaha.review.models import ReviewerAccountModel
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.integration.test_relation_proposals import setup

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def reviewer(h: StoreHarness) -> ReviewerPrincipal:
    p = replace(h.principal, reviewer_id=uuid7())
    with h.factory.begin() as s:
        s.add(
            ReviewerAccountModel(
                reviewer_id=p.reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"synthetic-review-test-{p.reviewer_id}",
                roles=[r.value for r in p.roles],
                allowed_purposes=list(p.purposes),
                created_at=h.clock(),
            )
        )
    return p


def request(
    saved: dict[str, Any], previous: str | None = None, decision: str = "APPROVE"
) -> DecideRelation:
    return DecideRelation.model_validate(
        {
            "proposal_id": saved["proposal_id"],
            "expected_proposal_payload_hash": saved["proposal_payload_sha256"],
            "previous_decision_id": previous,
            "decision": decision,
            "reason": "Synthetic independent interpretation review",
        }
    )


def test_independent_revision_retry_and_current_read(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    p = reviewer(h)
    first = save_relation_decision(h.store, task, request(saved), p, "approve")
    assert save_relation_decision(h.store, task, request(saved), p, "approve") == first
    refreshed = load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), p)
    assert refreshed["proposal_payload_sha256"] == saved["payload_sha256"]
    assert refreshed["payload_sha256"] != refreshed["proposal_payload_sha256"]
    second = save_relation_decision(
        h.store, task, request(refreshed, first["decision"]["decision_id"], "REJECT"), p, "reject"
    )
    read = load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), h.principal)
    assert read["package"]["proposal"] == saved["package"]["proposal"]
    assert read["review"]["status"] == "REJECTED" and not read["review"]["executable"]
    assert read["package"]["decisions"] == [first["decision"], second["decision"]]
    retry = save_relation_decision(h.store, task, request(saved), p, "approve")
    assert retry["decision"] == first["decision"] and retry["review"]["status"] == "REJECTED"


@pytest.mark.parametrize("attack", ["self", "hash", "previous", "idempotency"])
def test_invalid_decision_does_not_append(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    p = reviewer(h)
    first = save_relation_decision(h.store, task, request(saved), p, "first")
    command = request(saved, first["decision"]["decision_id"]).model_dump(mode="json")
    key = "next"
    if attack == "self":
        p = h.principal
    elif attack == "hash":
        command["expected_proposal_payload_hash"] = "0" * 64
    elif attack == "previous":
        command["previous_decision_id"] = None
    else:
        command["reason"], key = "Another interpretation", "first"
    with pytest.raises(InvestigationError):
        save_relation_decision(h.store, task, DecideRelation.model_validate(command), p, key)
    with h.factory() as s:
        assert s.scalar(text("SELECT count(*) FROM investigation_relation_decisions")) == 1


def test_decision_history_is_immutable(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    save_relation_decision(h.store, task, request(saved), reviewer(h), "approve")
    for sql in [
        "UPDATE investigation_relation_decisions SET payload_text='{}'",
        "DELETE FROM investigation_relation_decisions",
    ]:
        with pytest.raises(DBAPIError), h.factory.begin() as s:
            s.execute(text(sql))
    with pytest.raises(RuntimeError, match="RELATION_DECISION_HISTORY_DOWNGRADE_REFUSED"):
        migration_command.downgrade(Config("alembic.ini"), "20260910_0050")


def test_stale_read_and_retry_never_restore_approval(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    p = reviewer(h)
    first = save_relation_decision(h.store, task, request(saved), p, "approve")
    group = saved["package"]["proposal"]["source_review"]["dependencies"]["group"]["dependencies"][
        "group_source"
    ]
    latest = next(iter(group["applicability_histories"].values()))[-1]
    revised = DecideGroupApplicability.model_validate(
        latest["request"]
        | {"previous_decision_id": latest["decision_id"], "outcome": "DOES_NOT_APPLY"}
    )
    save_group_applicability(h.store, task, revised, h.principal, "exclude")
    loaded = load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), p)
    assert loaded["review"]["status"] == "STALE" and not loaded["review"]["executable"]
    assert (
        save_relation_decision(h.store, task, request(saved), p, "approve")["review"]["status"]
        == "STALE"
    )
    with pytest.raises(InvestigationError, match="RELATION_PROPOSAL_CONTEXT_CHANGED"):
        save_relation_decision(
            h.store, task, request(saved, first["decision"]["decision_id"], "REJECT"), p, "reject"
        )


def test_concurrent_reviewers_cannot_fork_history(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    principals = [reviewer(h), reviewer(h)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(save_relation_decision, h.store, task, request(saved), p, "approve")
            for p in principals
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=60)["review"]["status"])
            except InvestigationError as exc:
                outcomes.append(str(exc))
    assert sorted(outcomes) == ["APPROVED", "RELATION_DECISION_PREVIOUS_CHANGED"]


def test_post_flush_revocation_rolls_back(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    p = reviewer(h)
    calls = 0

    def revoke(session: Session, principal: ReviewerPrincipal) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            account = session.get(ReviewerAccountModel, principal.reviewer_id)
            assert account is not None
            account.active = False
            session.flush()
        _authorize(session, principal)

    monkeypatch.setattr("deepaha.investigations.relation_proposals._authorize", revoke)
    with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        save_relation_decision(h.store, task, request(saved), p, "approve")
    assert calls == 2
    with h.factory() as s:
        assert s.scalar(text("SELECT count(*) FROM investigation_relation_decisions")) == 0


def test_unresolved_relation_cannot_be_approved(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, proposal_request = setup(h, monkeypatch)
    proposal_request = proposal_request.model_copy(update={"relation": "UNRESOLVED"})
    saved = save_relation_proposal(h.store, task, proposal_request, h.principal, "proposal")
    p = reviewer(h)
    with pytest.raises(InvestigationError, match="RELATION_DECISION_INVALID"):
        save_relation_decision(h.store, task, request(saved), p, "approve")
    result = save_relation_decision(
        h.store, task, request(saved, decision="NEEDS_ADJUDICATION"), p, "needs"
    )
    assert result["review"]["status"] == "NEEDS_ADJUDICATION"
    assert not result["review"]["executable"]
