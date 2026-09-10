"""Read-only projections use synthetic approvals, never real human acceptance."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_facts import _describe, act_on_group_facts, prepare_group_facts
from deepaha.investigations.group_rules import preview_group_rules
from deepaha.p9b.facts import FactLifecycleService
from deepaha.p9b.identity import OpportunityUnitService
from deepaha.p9b.models import VerifiedFact, VerifiedFactEvidence, VerifiedFactSetDependency
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration.test_group_facts import decision_for, promote_for, ready_group
from tests.integration.test_investigation_store import StoreHarness, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def prepared(
    h: StoreHarness, monkeypatch: pytest.MonkeyPatch, **options: Any
) -> tuple[UUID, dict[str, Any]]:
    task, group, command = ready_group(h, monkeypatch, **options)
    return task, prepare_group_facts(h.store, task, group, command, h.principal)


def promote(h: StoreHarness, task: UUID, prep: dict[str, Any], *decisions: str) -> None:
    prep_id = UUID(prep["preparation_id"])
    for index, decision in enumerate(decisions):
        act_on_group_facts(
            h.store,
            task,
            prep_id,
            decision_for(prep, decision, index),
            h.principal,
            f"decision-{index}",
        )
    act_on_group_facts(h.store, task, prep_id, promote_for(prep), h.principal, "promote")


def test_group_preview_exact_target_all_rows_stable_and_no_writes(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, prep = prepared(h, monkeypatch, two=True, other_field="户籍要求")
    promote(h, task, prep, "APPROVE", "UNKNOWN")
    statements: list[str] = []

    def capture(
        _conn: Any, _cursor: Any, statement: str, _parameters: Any, _context: Any, _many: bool
    ) -> None:
        statements.append(statement)

    with h.factory() as session:
        engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = preview_group_rules(h.store, task, UUID(prep["preparation_id"]), h.principal)
        assert (
            preview_group_rules(h.store, task, UUID(prep["preparation_id"]), h.principal) == result
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any(
        s.lstrip().split()[0].upper()
        in {"INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE"}
        for s in statements
    )
    data = result["result"]
    assert result["result_hash"] == digest(data)
    assert data["scope"] == "READ_ONLY_GROUP_RULE_PREVIEW"
    assert data["target"] == prep["result"]["group_source"]["group_identity"]
    assert data["fact_review"]["result"] == prep["result"]
    assert len(data["rows"]) == 2
    known, unknown = data["rows"]
    assert known["proposed_rule_payload"]["value"] == "MASTER"
    assert known["reason_code"] == "INDEPENDENT_RULE_REVIEW_REQUIRED"
    assert known["evidence_ref_ids"]
    assert unknown["proposed_rule_payload"] is None
    assert unknown["reason_code"] == "FACT_UNKNOWN"
    assert unknown["fact_state"] == "UNKNOWN" and unknown["normalized_value"] is None
    assert [r["source_index"] for r in data["rows"]] == [
        r["source_index"] for r in prep["result"]["rows"]
    ]


@pytest.mark.parametrize(
    "options,reason",
    [
        ({}, "FACT_SET_NOT_SAVED"),
        ({"status": "UNKNOWN"}, "FACT_SET_NOT_SAVED"),
        ({"unverified": True}, "GROUP_FIELD_UNPROCESSED"),
        ({"field": "尚不支持的组字段"}, "GROUP_FIELD_UNPROCESSED"),
        ({"empty": True}, None),
    ],
)
def test_unreviewed_and_unprocessed_fields_never_propose_rules(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
    reason: str | None,
) -> None:
    task, prep = prepared(harness, monkeypatch, **options)
    data = preview_group_rules(
        harness.store, task, UUID(prep["preparation_id"]), harness.principal
    )["result"]
    assert data["fact_review"]["result"] == prep["result"]
    assert all(r["proposed_rule_payload"] is None for r in data["rows"])
    if reason:
        assert data["rows"][0]["reason_code"] == reason
    else:
        assert data["rows"] == [] and data["fact_review"]["result"]["excluded_rows"]


def test_rejected_row_is_retained_after_other_fact_saved(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, prep = prepared(harness, monkeypatch, two=True)
    promote(harness, task, prep, "APPROVE", "REJECT")
    rows = preview_group_rules(
        harness.store, task, UUID(prep["preparation_id"]), harness.principal
    )["result"]["rows"]
    assert len(rows) == 2 and rows[1]["reason_code"] == "FACT_REJECTED"
    assert rows[1]["verified_fact_id"] is None and rows[1]["proposed_rule_payload"] is None


@pytest.mark.parametrize("change", ["authority", "policy", "clock", "task", "preparation"])
def test_every_preview_rechecks_context(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, prep = prepared(h, monkeypatch)
    promote(h, task, prep, "APPROVE")
    prep_id = UUID(prep["preparation_id"])
    preview_group_rules(h.store, task, prep_id, h.principal)
    if change == "authority":
        with h.factory.begin() as session:
            account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
            assert account is not None
            account.active = False
    elif change == "policy":
        with h.factory.begin() as session:
            endpoint = session.scalar(select(SourceEndpoint))
            assert endpoint is not None
            endpoint.policy_version = "changed"
    elif change == "clock":
        h.clock.value -= timedelta(seconds=1)
    elif change == "task":
        task = uuid7()
    else:
        prep_id = uuid7()
    with pytest.raises(InvestigationError):
        preview_group_rules(h.store, task, prep_id, h.principal)


@pytest.mark.parametrize("status", ["UNKNOWN", "CONFLICT"])
def test_unknown_and_conflict_saved_facts_do_not_become_rules(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    task, prep = prepared(harness, monkeypatch, status=status)
    promote(harness, task, prep, "UNKNOWN")
    data = preview_group_rules(
        harness.store, task, UUID(prep["preparation_id"]), harness.principal
    )["result"]
    assert data["rows"][0]["reason_code"] == "FACT_UNKNOWN"
    assert data["rows"][0]["proposed_rule_payload"] is None
    assert data["fact_review"]["result"]["rows"][0]["original"]["status"] == status


def test_active_fact_set_does_not_hide_unprocessed_group_field(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, prep = prepared(harness, monkeypatch, two=True, other_field="未支持的其他条件")
    promote(harness, task, prep, "APPROVE")
    data = preview_group_rules(
        harness.store, task, UUID(prep["preparation_id"]), harness.principal
    )["result"]
    assert data["fact_review"]["fact_set"]["status"] == "ACTIVE"
    assert len(data["rows"]) == 2
    assert data["rows"][1]["reason_code"] == "GROUP_FIELD_UNPROCESSED"
    assert data["rows"][1]["proposed_rule_payload"] is None


def test_non_executable_known_metadata_is_not_a_qualification(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, prep = prepared(harness, monkeypatch, field="公告名称")
    promote(harness, task, prep, "APPROVE")
    row = preview_group_rules(harness.store, task, UUID(prep["preparation_id"]), harness.principal)[
        "result"
    ]["rows"][0]
    assert row["fact_state"] == "KNOWN"
    assert row["reason_code"] == "FIELD_NOT_EXECUTABLE"
    assert row["proposed_rule_payload"] is None


@pytest.mark.parametrize("change", ["group_version", "stale_fact_set"])
def test_changed_group_version_or_inactive_fact_set_cannot_use_previous_preview(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, prep = prepared(h, monkeypatch)
    promote(h, task, prep, "APPROVE")
    prep_id = UUID(prep["preparation_id"])
    initial = preview_group_rules(h.store, task, prep_id, h.principal)
    h.clock.value += timedelta(seconds=1)
    with h.factory.begin() as session:
        if change == "group_version":
            identity = prep["result"]["group_source"]["group_identity"]
            source = prep["result"]["group_source"]["source"]
            OpportunityUnitService(session).append_version_cas(
                opportunity_unit_id=UUID(identity["unit_id"]),
                expected_current_version_id=UUID(identity["unit_version_id"]),
                opportunity_version=source["opportunity_version"],
                source_bundle_revision_id=UUID(source["source_bundle_revision_id"]),
                effective_from=h.clock.value,
                canonical_label="Changed group",
                identity_fingerprint="d" * 64,
            )
            code = "GROUP_IDENTITY_INTEGRITY_FAILED"
        else:
            fact_set_id = UUID(initial["result"]["fact_review"]["fact_set"]["fact_set_id"])
            dependency = session.scalar(
                select(VerifiedFactSetDependency).where(
                    VerifiedFactSetDependency.verified_fact_set_id == fact_set_id
                )
            )
            assert dependency is not None
            FactLifecycleService(session).invalidate_dependency(
                verified_fact_set_id=fact_set_id,
                dependency_id=dependency.dependency_id,
                observed_dependency_fingerprint="f" * 64,
                reason_code="SYNTHETIC_DEPENDENCY_CHANGED",
                actor_identity=f"human:{h.principal.reviewer_id}",
                created_at=h.clock.value,
            )
            code = "GROUP_RULE_FACT_SET_NOT_ACTIVE"
    with pytest.raises(InvestigationError, match=code):
        preview_group_rules(h.store, task, prep_id, h.principal)


def test_evidence_appended_by_another_transaction_after_validation_is_rejected(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.investigations import group_rules

    h = harness
    task, prep = prepared(h, monkeypatch, two_evidence=True, other_field="户籍要求")
    promote(h, task, prep, "APPROVE", "UNKNOWN")

    def interleave(*args: Any) -> dict[str, Any]:
        checked = _describe(*args)
        # Commit on a second connection after the initial integrity check. All
        # real constraints remain enabled; no trigger bypass or mocked evidence.
        with h.factory.begin() as session:
            first = session.scalar(
                select(VerifiedFact).where(VerifiedFact.field_name == "education_requirements")
            )
            other = session.scalar(
                select(VerifiedFactEvidence)
                .join(
                    VerifiedFact,
                    VerifiedFact.verified_fact_id == VerifiedFactEvidence.verified_fact_id,
                )
                .where(VerifiedFact.field_name == "household_registration_requirements")
            )
            assert first is not None and other is not None
            session.add(
                VerifiedFactEvidence(
                    verified_fact_id=first.verified_fact_id,
                    verified_fact_set_id=first.verified_fact_set_id,
                    candidate_id=other.candidate_id,
                    block_id=other.block_id,
                    evidence_ref_id=other.evidence_ref_id,
                )
            )
        return checked

    monkeypatch.setattr(group_rules, "_describe", interleave)
    with pytest.raises(InvestigationError, match="GROUP_FACT_MATERIALIZATION_INTEGRITY_FAILED"):
        preview_group_rules(h.store, task, UUID(prep["preparation_id"]), h.principal)
