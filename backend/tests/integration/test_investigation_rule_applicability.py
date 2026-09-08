"""Synthetic independent applicability records; no inherited or final qualification."""

from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.applicability import (
    DecideRuleApplicability,
    read_rule_applicability,
    save_rule_applicability,
)
from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    InvestigationError,
    PromoteInvestigationFacts,
)
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.models import InvestigationRuleApplicability
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.investigations.unit_snapshots import load_unit_plan, materialize_unit_plan
from tests.integration.test_investigation_facts import _ready
from tests.integration.test_investigation_rules import _decision
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def prepared(h: StoreHarness, *, duplicate_materials: int = 0) -> tuple[UUID, UUID, UUID, UUID]:
    task, base = _ready(h, announcement=True, duplicate_materials=duplicate_materials)
    prep = prepare_facts(h.store, task, base, h.principal)["current"]
    common = base.model_dump() | {
        "preparation_id": prep["preparation_id"],
        "reason": "Synthetic engineering review only",
    }
    plans: dict[str, dict[str, Any]] = {}
    for row in prep["rows"]:
        act_on_facts(
            h.store,
            task,
            DecideInvestigationFact.model_validate(
                common
                | {
                    "candidate_id": row["candidate_id"],
                    "decision": "APPROVE",
                    "evidence_support": "SUPPORTED",
                    "precedence_check": "PASSED",
                }
            ),
            h.principal,
            "fact-" + row["entity_id"],
        )
    for entity in ("announcement", "position"):
        facts = act_on_facts(
            h.store,
            task,
            PromoteInvestigationFacts.model_validate(common | {"entity_id": entity}),
            h.principal,
            "promote-" + entity,
        )
        command = MaterializeInvestigationUnitPlan.model_validate(
            base.model_dump()
            | {
                "fact_preparation_id": prep["preparation_id"],
                "entity_id": entity,
                "fact_set_id": facts["current"]["promotions"][entity]["fact_set_id"],
                "rule_preparation_id": uuid7(),
            }
        )
        rules = prepare_rules(h.store, task, command, h.principal)
        command = command.model_copy(
            update={"rule_preparation_id": UUID(rules["rule_preparation_id"])}
        )
        decide_rule(h.store, task, _decision(command, rules), h.principal, "rule-" + entity)
        plans[entity] = rules
        if entity == "position":
            snapshot = materialize_unit_plan(h.store, task, command, h.principal)
    return (
        task,
        UUID(snapshot["plan_id"]),
        UUID(plans["announcement"]["rule_preparation_id"]),
        UUID(plans["announcement"]["rows"][0]["rule_candidate_id"]),
    )


def command(view: dict[str, Any], **changes: Any) -> DecideRuleApplicability:
    block = view["evidence_options"][0]
    return DecideRuleApplicability.model_validate(
        {
            "target_plan_id": view["context"]["target_plan_id"],
            "source_rule_preparation_id": view["context"]["source_rule_preparation_id"],
            "source_rule_candidate_id": view["context"]["source_rule_candidate_id"],
            "context_hash": view["context_hash"],
            "previous_decision_id": view["latest"]["decision_id"] if view["latest"] else None,
            "outcome": "APPLIES",
            "evidence": [
                {
                    "member_id": block["member_id"],
                    "block_id": block["block_id"],
                    "quote": block["text"],
                }
            ],
            "reason": "Synthetic exact scope review, not a real human decision",
            **changes,
        }
    )


def test_application_is_append_only_repeatable_and_does_not_change_plan(
    harness: StoreHarness,
) -> None:
    h = harness
    task, plan, source, candidate = prepared(h)
    before = load_unit_plan(h.store, task, plan, h.principal)
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    assert view["latest"] is None and view["history"] == []
    pending = command(view, outcome="NEEDS_ADJUDICATION", evidence=[])
    first = save_rule_applicability(h.store, task, pending, h.principal, "pending")
    assert save_rule_applicability(h.store, task, pending, h.principal, "pending") == first
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    second = save_rule_applicability(h.store, task, command(view), h.principal, "applies")
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    assert view["latest"] == second and len(view["history"]) == 2
    assert second["request"]["previous_decision_id"] == first["decision_id"]
    save_rule_applicability(
        h.store, task, command(view, outcome="DOES_NOT_APPLY"), h.principal, "fix"
    )
    assert load_unit_plan(h.store, task, plan, h.principal) == before
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationRuleApplicability)))) == 3


@pytest.mark.parametrize("attack", ["context", "foreign-block", "quote", "predecessor", "key"])
def test_rejects_stale_or_unbound_decisions(harness: StoreHarness, attack: str) -> None:
    h = harness
    task, plan, source, candidate = prepared(h)
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    body = command(view).model_dump(mode="json")
    if attack == "context":
        body["context_hash"] = "0" * 64
    elif attack == "foreign-block":
        body["evidence"][0]["block_id"] = str(uuid7())
    elif attack == "quote":
        body["evidence"][0]["quote"] = "This text is not in the official fixture"
    else:
        save_rule_applicability(h.store, task, command(view), h.principal, "initial")
        if attack == "key":
            body["reason"] = "Changed request with the same key"
    with pytest.raises(InvestigationError):
        save_rule_applicability(
            h.store,
            task,
            DecideRuleApplicability.model_validate(body),
            h.principal,
            "initial" if attack == "key" else "invalid",
        )


def test_current_evidence_rechecked_even_for_identical_retry(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, plan, source, candidate = prepared(h)
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    body = command(view)
    save_rule_applicability(h.store, task, body, h.principal, "initial")
    monkeypatch.setattr("deepaha.investigations.evidence_checks.VERIFIER_VERSION", "synthetic-next")
    with pytest.raises(InvestigationError, match="EVIDENCE_CHECK_REFRESH_REQUIRED"):
        save_rule_applicability(h.store, task, body, h.principal, "initial")
    with pytest.raises(InvestigationError, match="EVIDENCE_CHECK_REFRESH_REQUIRED"):
        read_rule_applicability(h.store, task, plan, source, candidate, h.principal)


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_database_history_cannot_be_changed(harness: StoreHarness, operation: str) -> None:
    h = harness
    task, plan, source, candidate = prepared(h)
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    save_rule_applicability(h.store, task, command(view), h.principal, "initial")
    sql = (
        "UPDATE investigation_rule_applicability SET sequence=2"
        if operation == "UPDATE"
        else "DELETE FROM investigation_rule_applicability"
    )
    with pytest.raises(DBAPIError, match="IMMUTABLE"), h.factory.begin() as session:
        session.execute(text(sql))


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_review_requires_current_predecessor(
    harness: StoreHarness, same_key: bool
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    h = harness
    task, plan, source, candidate = prepared(h)
    body = command(read_rule_applicability(h.store, task, plan, source, candidate, h.principal))

    def submit(key: str) -> object:
        try:
            return save_rule_applicability(h.store, task, body, h.principal, key)
        except InvestigationError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ("same", "same" if same_key else "other")))
    if same_key:
        assert outcomes[0] == outcomes[1]
    else:
        assert sum(isinstance(x, dict) for x in outcomes) == 1
        assert "RULE_APPLICABILITY_PREDECESSOR_CHANGED" in outcomes
    assert (
        len(read_rule_applicability(h.store, task, plan, source, candidate, h.principal)["history"])
        == 1
    )


@pytest.mark.parametrize("attack", ["task", "candidate", "source-scope"])
def test_no_cross_task_or_nonannouncement_source(harness: StoreHarness, attack: str) -> None:
    h = harness
    task, plan, source, candidate = prepared(h)
    if attack == "task":
        task = uuid7()
    elif attack == "candidate":
        candidate = uuid7()
    else:
        snapshot = load_unit_plan(h.store, task, plan, h.principal)
        source = UUID(snapshot["context"]["rule_preparation_id"])
        candidate = UUID(snapshot["plan"]["rules"][0]["rule_id"])
    with pytest.raises(InvestigationError):
        read_rule_applicability(h.store, task, plan, source, candidate, h.principal)


@pytest.mark.parametrize("attack", ["null-outcome", "missing-quote", "wrong-target"])
def test_raw_sql_cannot_forge_required_review_fields(harness: StoreHarness, attack: str) -> None:
    from copy import deepcopy

    from sqlalchemy import insert

    from deepaha.investigations.contracts import digest

    h = harness
    task, plan, source, candidate = prepared(h)
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    saved = save_rule_applicability(h.store, task, command(view), h.principal, "initial")
    with h.factory() as session:
        row = session.get(InvestigationRuleApplicability, UUID(saved["decision_id"]))
        assert row is not None
        values = {c.name: deepcopy(getattr(row, c.name)) for c in row.__table__.columns}
    values.update(
        decision_id=uuid7(),
        previous_decision_id=UUID(saved["decision_id"]),
        sequence=2,
        request_key_hash="a" * 64,
    )
    values["request"]["previous_decision_id"] = saved["decision_id"]
    if attack == "null-outcome":
        values["request"]["outcome"] = None
    elif attack == "missing-quote":
        del values["request"]["evidence"][0]["quote"]
        del values["evidence_snapshot"][0]["quote"]
    else:
        values["context"]["target"]["unit_version_id"] = str(uuid7())
    values["context_hash"] = digest(values["context"])
    values["request"]["context_hash"] = values["context_hash"]
    values["request_hash"] = digest(values["request"])
    values["evidence_hash"] = digest(values["evidence_snapshot"])
    with pytest.raises(DBAPIError, match="RULE_APPLICABILITY"), h.factory.begin() as session:
        session.execute(insert(InvestigationRuleApplicability).values(**values))


def test_history_prevents_schema_downgrade(harness: StoreHarness) -> None:
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    h = harness
    task, plan, source, candidate = prepared(h)
    view = read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    save_rule_applicability(h.store, task, command(view), h.principal, "initial")
    migration = import_module("migrations.versions.20260908_0043_announcement_rule_applicability")
    with (
        h.factory.begin() as session,
        Operations.context(MigrationContext.configure(session.connection())),
        pytest.raises(RuntimeError, match="HISTORY_DOWNGRADE_REFUSED"),
    ):
        migration.downgrade()


def test_revoked_reviewer_cannot_read_or_retry(harness: StoreHarness) -> None:
    from sqlalchemy import update

    from deepaha.review.models import ReviewerAccountModel

    h = harness
    task, plan, source, candidate = prepared(h)
    body = command(read_rule_applicability(h.store, task, plan, source, candidate, h.principal))
    save_rule_applicability(h.store, task, body, h.principal, "initial")
    with h.factory.begin() as session:
        session.execute(
            update(ReviewerAccountModel)
            .where(ReviewerAccountModel.reviewer_id == h.principal.reviewer_id)
            .values(active=False)
        )
    with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        read_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        save_rule_applicability(h.store, task, body, h.principal, "initial")


def test_evidence_pagination_preserves_every_member_of_shared_blocks(harness: StoreHarness) -> None:
    from deepaha.documents.models import DocumentBlock
    from deepaha.p9b.models import SourceBundleMember

    h = harness
    task, plan, source, candidate = prepared(h, duplicate_materials=51)
    with h.factory() as session:
        expected = {
            (str(member_id), str(block_id))
            for member_id, block_id in session.execute(
                select(SourceBundleMember.source_bundle_member_id, DocumentBlock.block_id)
                .join(DocumentBlock, DocumentBlock.document_id == SourceBundleMember.document_id)
                .where(SourceBundleMember.wma_task_id == task)
            )
        }
    assert len(expected) > 50
    observed: list[tuple[str, str]] = []
    cursor = None
    for _ in range(10):
        page = read_rule_applicability(
            h.store, task, plan, source, candidate, h.principal, after=cursor
        )
        observed.extend((item["member_id"], item["block_id"]) for item in page["evidence_options"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert len(observed) == len(set(observed))
    assert set(observed) == expected


def test_private_http_review_retries_once_and_revocation_is_forbidden(
    harness: StoreHarness,
) -> None:
    from typing import cast

    from fastapi import FastAPI
    from sqlalchemy import update

    from deepaha.api.investigations import get_investigation_store
    from deepaha.api.local_human_test import require_local_test_principal
    from deepaha.review.models import ReviewerAccountModel
    from tests.api.test_investigations import make_client

    h = harness
    task, plan, source, candidate = prepared(h)
    client, _ = make_client(h.object_root)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    root = f"/api/v1/local-human-test/investigations/{task}"
    path = f"{root}/unit-plans/{plan}/rule-applicability/{source}/{candidate}"
    with client:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json()["evidence_options"][0]["source_url"].startswith("https://")
        body = command(response.json()).model_dump(mode="json")
        first = client.post(
            root + "/rule-applicability", json=body, headers={"Idempotency-Key": "http-retry"}
        )
        assert first.status_code == 200
        retry = client.post(
            root + "/rule-applicability", json=body, headers={"Idempotency-Key": "http-retry"}
        )
        assert retry.json() == first.json()
        assert client.get(path).json()["latest"] == first.json()
        with h.factory.begin() as session:
            session.execute(
                update(ReviewerAccountModel)
                .where(ReviewerAccountModel.reviewer_id == h.principal.reviewer_id)
                .values(active=False)
            )
        forbidden = client.get(path)
        assert forbidden.status_code == 403
        assert forbidden.headers["cache-control"] == "private, no-store"
        assert "context" not in forbidden.json()
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationRuleApplicability)))) == 1
