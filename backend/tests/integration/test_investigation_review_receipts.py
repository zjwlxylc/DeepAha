"""Synthetic committed receipts; not human approval evidence."""

from dataclasses import replace
from uuid import UUID, uuid7

import pytest

from deepaha.investigations.contracts import DecideInvestigationFact
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.review_receipts import read_review_receipt
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.review.models import ReviewerAccountModel
from tests.integration.test_investigation_facts import _ready
from tests.integration.test_investigation_rules import _decision, _facts
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_receipt_distinguishes_missing_from_committed(harness: StoreHarness) -> None:
    h = harness
    task_id, command = _ready(h)
    prep = prepare_facts(h.store, task_id, command, h.principal)["current"]
    preparation_id = UUID(prep["preparation_id"])
    key = "a" * 64
    assert not read_review_receipt(h.store, task_id, "FACT", preparation_id, key, h.principal)[
        "committed"
    ]
    decision = DecideInvestigationFact.model_validate(
        command.model_dump()
        | {
            "preparation_id": preparation_id,
            "candidate_id": prep["rows"][0]["candidate_id"],
            "reason": "Synthetic pending evidence",
            "decision": "NEEDS_ADJUDICATION",
            "evidence_support": "UNKNOWN",
            "precedence_check": "UNKNOWN",
        }
    )
    act_on_facts(h.store, task_id, decision, h.principal, key)
    receipt = read_review_receipt(h.store, task_id, "FACT", preparation_id, key, h.principal)
    assert receipt["committed"] and receipt["receipt_id"]
    other = replace(h.principal, reviewer_id=uuid7())
    with h.factory.begin() as session:
        session.add(
            ReviewerAccountModel(
                reviewer_id=other.reviewer_id,
                active=True,
                synthetic=False,
                principal_label="synthetic-other-reviewer",
                roles=[role.value for role in other.roles],
                allowed_purposes=list(other.purposes),
                created_at=h.clock(),
            )
        )
    assert not read_review_receipt(h.store, task_id, "FACT", preparation_id, key, other)[
        "committed"
    ]
    assert not read_review_receipt(h.store, task_id, "RULE", preparation_id, key, h.principal)[
        "committed"
    ]
    assert not read_review_receipt(h.store, task_id, "FACT", preparation_id, "b" * 64, h.principal)[
        "committed"
    ]


def test_rule_receipt_matches_persisted_task_and_preparation(harness: StoreHarness) -> None:
    h = harness
    task_id, command = _facts(h)
    prep = prepare_rules(h.store, task_id, command, h.principal)
    preparation_id = UUID(prep["rule_preparation_id"])
    key = "c" * 64
    assert not read_review_receipt(h.store, task_id, "RULE", preparation_id, key, h.principal)[
        "committed"
    ]
    decide_rule(h.store, task_id, _decision(command, prep), h.principal, key)
    assert read_review_receipt(h.store, task_id, "RULE", preparation_id, key, h.principal)[
        "committed"
    ]
    assert not read_review_receipt(h.store, task_id, "RULE", uuid7(), key, h.principal)["committed"]
