"""Real proposal persistence; all sources and reviewer accounts are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any
from uuid import UUID, uuid7

import pytest
from alembic import command as migration_command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.cross_level_preview import preview_cross_level
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decisions import (
    DecideGroupApplicability,
    save_group_applicability,
)
from deepaha.investigations.relation_proposals import (
    ProposeRelation,
    load_relation_proposal,
    save_relation_proposal,
)
from deepaha.review.auth import ReviewerPrincipal
from deepaha.review.models import ReviewerAccountModel
from tests.integration.test_group_applicability_decisions import command as scope_command
from tests.integration.test_group_rule_applicability import prepared
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def setup(h: StoreHarness, monkeypatch: pytest.MonkeyPatch) -> tuple[UUID, ProposeRelation]:
    task, plan, group, candidate = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, task, plan, group, candidate, h.principal)
    save_group_applicability(h.store, task, scope_command(view), h.principal, "applies")
    review = preview_cross_level(h.store, task, plan, h.principal)
    selected = [
        r["condition"]["condition_id"]
        for r in review["snapshot"]["conditions"]
        if r["disposition"] in {"LOCAL", "INHERITED"}
    ]
    e = view["evidence_options"][0]
    request = ProposeRelation.model_validate(
        {
            "target_plan_id": plan,
            "expected_review_hash": digest(review),
            "condition_ids": selected,
            "relation": "CUMULATIVE",
            "displaced_condition_ids": [],
            "reason": "Synthetic proposal, not verified human semantics",
            "evidence": [
                {
                    "purpose": p,
                    "condition_ids": selected,
                    "member_id": e["member_id"],
                    "block_id": e["block_id"],
                    "quote": e["text"],
                }
                for p in ("CONDITION", "RELATION")
            ],
        }
    )
    return task, request


def test_save_retry_and_read_preserve_complete_unapproved_package(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    task, request = setup(h, monkeypatch)
    before = preview_cross_level(h.store, task, request.target_plan_id, h.principal)
    saved = save_relation_proposal(h.store, task, request, h.principal, "first")
    assert save_relation_proposal(h.store, task, request, h.principal, "first") == saved
    loaded = load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), h.principal)
    assert loaded == saved
    assert saved["package"]["decisions"] == []
    assert saved["package"]["proposal"]["producer_id"] == str(h.principal.reviewer_id)
    assert saved["package"]["proposal"]["source_review"] == before
    assert saved["review"]["status"] == "UNREVIEWED" and not saved["review"]["executable"]
    assert preview_cross_level(h.store, task, request.target_plan_id, h.principal) == before


@pytest.mark.parametrize("attack", ["quote", "member", "hash", "idempotency", "target"])
def test_failed_save_does_not_append(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    h = harness
    task, request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, request, h.principal, "first")
    changed: dict[str, Any] = deepcopy(request.model_dump(mode="json"))
    key = "second"
    if attack == "quote":
        changed["evidence"][0]["quote"] = "forged quote"
    elif attack == "member":
        changed["evidence"][0]["member_id"] = str(uuid7())
    elif attack == "hash":
        changed["expected_review_hash"] = "0" * 64
    elif attack == "target":
        changed["target_plan_id"] = str(uuid7())
    else:
        changed["reason"], key = "Different request", "first"
    with pytest.raises(InvestigationError):
        save_relation_proposal(
            h.store, task, ProposeRelation.model_validate(changed), h.principal, key
        )
    with h.factory() as s:
        assert s.scalar(text("SELECT count(*) FROM investigation_relation_proposals")) == 1
    assert load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), h.principal) == saved


def test_database_refuses_proposal_mutation(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, request, h.principal, "first")
    for sql in [
        "UPDATE investigation_relation_proposals SET payload_text='{}'",
        "DELETE FROM investigation_relation_proposals",
    ]:
        with pytest.raises(DBAPIError), h.factory.begin() as s:
            s.execute(text(sql))
    with pytest.raises(RuntimeError, match="RELATION_PROPOSAL_HISTORY_DOWNGRADE_REFUSED"):
        migration_command.downgrade(Config("alembic.ini"), "20260910_0049")
    assert load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), h.principal) == saved


def test_changed_source_is_stale_and_retry_cannot_reuse_old_scope(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    task, request = setup(h, monkeypatch)
    saved = save_relation_proposal(h.store, task, request, h.principal, "first")
    group = saved["package"]["proposal"]["source_review"]["dependencies"]["group"]["dependencies"][
        "group_source"
    ]
    latest = next(iter(group["applicability_histories"].values()))[-1]
    revised = DecideGroupApplicability.model_validate(
        latest["request"]
        | {"previous_decision_id": latest["decision_id"], "outcome": "DOES_NOT_APPLY"}
    )
    save_group_applicability(h.store, task, revised, h.principal, "exclude")
    loaded = load_relation_proposal(h.store, task, UUID(saved["proposal_id"]), h.principal)
    assert loaded["package"] == saved["package"]
    assert loaded["review"]["status"] == "STALE" and not loaded["review"]["executable"]
    with pytest.raises(InvestigationError, match="RELATION_PROPOSAL_CONTEXT_CHANGED"):
        save_relation_proposal(h.store, task, request, h.principal, "first")


@pytest.mark.parametrize("revoke_at", [2, 3])
def test_revocation_at_recheck_rolls_back_proposal(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, revoke_at: int
) -> None:
    h = harness
    task, request = setup(h, monkeypatch)
    calls = 0

    def revoke(session: Session, principal: ReviewerPrincipal) -> None:
        nonlocal calls
        calls += 1
        if calls == revoke_at:
            account = session.get(ReviewerAccountModel, principal.reviewer_id)
            assert account is not None
            account.active = False
            session.flush()
        _authorize(session, principal)

    monkeypatch.setattr("deepaha.investigations.relation_proposals._authorize", revoke)
    with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        save_relation_proposal(h.store, task, request, h.principal, "revoked")
    assert calls == revoke_at
    with h.factory() as session:
        assert session.scalar(text("SELECT count(*) FROM investigation_relation_proposals")) == 0


def test_concurrent_same_key_creates_one_proposal(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, request = setup(h, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(save_relation_proposal, h.store, task, request, h.principal, "shared")
            for _ in range(2)
        ]
        results = [future.result(timeout=60) for future in futures]
    assert results[0] == results[1]
    with h.factory() as session:
        assert session.scalar(text("SELECT count(*) FROM investigation_relation_proposals")) == 1
