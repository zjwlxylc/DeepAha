"""Synthetic PG scope snapshots, never inherited eligibility approval."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, cast
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, insert, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.announcement_snapshots import (
    load_announcement_snapshot,
    materialize_announcement_snapshot,
    preview_announcement_snapshot,
)
from deepaha.investigations.applicability import read_rule_applicability, save_rule_applicability
from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    InvestigationError,
    PromoteInvestigationFacts,
    digest,
)
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.models import (
    InvestigationAnnouncementSnapshot,
    InvestigationRulePreparation,
)
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.investigations.unit_snapshots import load_unit_plan, materialize_unit_plan
from tests.integration.test_investigation_facts import _ready
from tests.integration.test_investigation_rule_applicability import command, prepared
from tests.integration.test_investigation_rules import _decision
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_announcement_snapshot_preserves_source_and_invalidates_after_correction(
    harness: StoreHarness,
) -> None:
    h = harness
    task, base_id, source, candidate = prepared(h)
    old_base = load_unit_plan(h.store, task, base_id, h.principal)
    initial = preview_announcement_snapshot(h.store, task, base_id, h.principal)
    assert initial["snapshot"]["scope"] == "DERIVED_SCOPE_SNAPSHOT_ONLY"
    assert initial["snapshot"]["base_v2"] == old_base
    assert initial["snapshot"]["announcement_conditions"][0]["disposition"] == "UNRESOLVED"
    pending = materialize_announcement_snapshot(
        h.store, task, base_id, initial["dependencies_hash"], h.principal
    )
    assert (
        materialize_announcement_snapshot(
            h.store, task, base_id, initial["dependencies_hash"], h.principal
        )
        == pending
    )
    review = read_rule_applicability(h.store, task, base_id, source, candidate, h.principal)
    applied = save_rule_applicability(h.store, task, command(review), h.principal, "apply")
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SNAPSHOT_STALE"):
        load_announcement_snapshot(h.store, task, UUID(pending["snapshot_id"]), h.principal)
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SNAPSHOT_INPUT_CHANGED"):
        materialize_announcement_snapshot(
            h.store, task, base_id, initial["dependencies_hash"], h.principal
        )
    current = preview_announcement_snapshot(h.store, task, base_id, h.principal)
    inherited = materialize_announcement_snapshot(
        h.store, task, base_id, current["dependencies_hash"], h.principal
    )
    row = inherited["snapshot"]["announcement_conditions"][0]
    assert row["disposition"] == "INHERITED"
    assert row["condition"]["scope"] == "ANNOUNCEMENT"
    assert row["condition"]["source_unit_id"] is None
    assert row["source_rule"]["rule_id"] == str(candidate)
    assert row["applicability"]["decision_id"] == applied["decision_id"]
    assert inherited["snapshot"]["base_v2"] == old_base
    assert inherited["snapshot_id"] != pending["snapshot_id"]
    assert load_unit_plan(h.store, task, base_id, h.principal) == old_base
    assert (
        load_announcement_snapshot(h.store, task, UUID(inherited["snapshot_id"]), h.principal)
        == inherited
    )

    review = read_rule_applicability(h.store, task, base_id, source, candidate, h.principal)
    excluded = save_rule_applicability(
        h.store,
        task,
        command(review, outcome="DOES_NOT_APPLY"),
        h.principal,
        "exclude",
    )
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SNAPSHOT_STALE"):
        load_announcement_snapshot(h.store, task, UUID(inherited["snapshot_id"]), h.principal)
    current = preview_announcement_snapshot(h.store, task, base_id, h.principal)
    assert current["snapshot"]["announcement_conditions"][0]["disposition"] == "EXCLUDED"
    assert current["snapshot"]["announcement_conditions"][0]["applicability"] == excluded
    assert current["snapshot"]["overall_qualification"] == "UNCERTAIN"


def partial_source(h: StoreHarness, stage: str) -> tuple[UUID, UUID]:
    task, base = _ready(
        h,
        announcement=stage != "no-announcement",
        status="UNKNOWN" if stage == "fact-unknown" else "CONFIRMED",
    )
    prep = prepare_facts(h.store, task, base, h.principal)["current"]
    common = base.model_dump() | {
        "preparation_id": prep["preparation_id"],
        "reason": "Synthetic engineering review only",
    }
    for entity in ("announcement", "position"):
        if entity == "announcement" and stage in ("no-announcement", "not-reviewed"):
            continue
        row = next(row for row in prep["rows"] if row["entity_id"] == entity)
        decision = "UNKNOWN" if stage == "fact-unknown" else "APPROVE"
        if entity == "announcement":
            decision = {"fact-unknown": "UNKNOWN", "fact-rejected": "REJECT"}.get(stage, decision)
        act_on_facts(
            h.store,
            task,
            DecideInvestigationFact.model_validate(
                common
                | {
                    "candidate_id": row["candidate_id"],
                    "decision": decision,
                    "evidence_support": "SUPPORTED",
                    "precedence_check": "PASSED",
                }
            ),
            h.principal,
            "fact-" + entity,
        )
        if entity == "announcement" and stage in ("not-promoted", "fact-rejected"):
            continue
        facts = act_on_facts(
            h.store,
            task,
            PromoteInvestigationFacts.model_validate(common | {"entity_id": entity}),
            h.principal,
            "promote-" + entity,
        )
        if entity == "announcement" and stage == "no-rule-preparation":
            continue
        body = MaterializeInvestigationUnitPlan.model_validate(
            base.model_dump()
            | {
                "fact_preparation_id": prep["preparation_id"],
                "entity_id": entity,
                "fact_set_id": facts["current"]["promotions"][entity]["fact_set_id"],
                "rule_preparation_id": uuid7(),
            }
        )
        rules = prepare_rules(h.store, task, body, h.principal)
        body = body.model_copy(update={"rule_preparation_id": UUID(rules["rule_preparation_id"])})
        if entity == "announcement" and stage in ("rule-unreviewed", "fact-unknown"):
            continue
        changes: dict[str, Any] = {}
        if entity == "announcement" and stage in ("rule-rejected", "rule-pending"):
            changes = {
                "decision": "REJECT" if stage == "rule-rejected" else "NEEDS_ADJUDICATION",
                "evidence": [],
            }
        if stage != "fact-unknown":
            decide_rule(
                h.store, task, _decision(body, rules, **changes), h.principal, "rule-" + entity
            )
        if entity == "position":
            return task, UUID(materialize_unit_plan(h.store, task, body, h.principal)["plan_id"])
    raise AssertionError("fixture must build a position")


@pytest.mark.parametrize(
    "stage,reason",
    [
        ("not-reviewed", "SOURCE_FACT_NOT_PROMOTED"),
        ("not-promoted", "SOURCE_FACT_NOT_PROMOTED"),
        ("fact-rejected", "SOURCE_FACT_REJECTED"),
        ("fact-unknown", "SOURCE_FACT_UNKNOWN"),
        ("no-rule-preparation", "SOURCE_RULE_PREPARATION_MISSING"),
        ("rule-unreviewed", "SOURCE_RULE_APPROVAL_REQUIRED"),
        ("rule-rejected", "SOURCE_RULE_REJECTED"),
        ("rule-pending", "SOURCE_RULE_GROUP_UNRESOLVED"),
    ],
)
def test_missing_or_rejected_source_is_preserved(
    harness: StoreHarness, stage: str, reason: str
) -> None:
    h = harness
    task, base = partial_source(h, stage)
    original = load_unit_plan(h.store, task, base, h.principal)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    saved = materialize_announcement_snapshot(
        h.store, task, base, preview["dependencies_hash"], h.principal
    )
    assert saved["snapshot"]["base_v2"] == original
    conditions = saved["snapshot"]["announcement_conditions"]
    assert len(conditions) == 1
    assert conditions[0]["disposition"] == "UNRESOLVED" and reason in conditions[0]["reasons"]
    assert saved["snapshot"]["overall_qualification"] == "UNCERTAIN"
    assert (
        load_announcement_snapshot(h.store, task, UUID(saved["snapshot_id"]), h.principal) == saved
    )


def test_no_announcement_retains_full_base_and_cannot_enter_v2_compiler(
    harness: StoreHarness,
) -> None:
    from pydantic import ValidationError

    from deepaha.unit_qualification.contracts import UnitQualificationPlan

    h = harness
    task, base = partial_source(h, "no-announcement")
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    saved = materialize_announcement_snapshot(
        h.store, task, base, preview["dependencies_hash"], h.principal
    )
    assert saved["snapshot"]["announcement_conditions"] == []
    assert saved["snapshot"]["base_v2"]["plan"]["manifest"]["conditions"]
    with pytest.raises(ValidationError):
        UnitQualificationPlan.model_validate(saved["snapshot"])


def test_every_latest_decision_even_same_outcome_invalidates_snapshot(
    harness: StoreHarness,
) -> None:
    h = harness
    task, base, source, candidate = prepared(h)
    previous = None
    seen: set[str] = set()
    for sequence, outcome in enumerate(
        ("NEEDS_ADJUDICATION", "DOES_NOT_APPLY", "APPLIES", "APPLIES")
    ):
        view = read_rule_applicability(h.store, task, base, source, candidate, h.principal)
        save_rule_applicability(
            h.store,
            task,
            command(view, outcome=outcome, reason=f"Synthetic correction {sequence}"),
            h.principal,
            str(sequence),
        )
        preview = preview_announcement_snapshot(h.store, task, base, h.principal)
        assert preview["dependencies_hash"] not in seen
        seen.add(preview["dependencies_hash"])
        if previous:
            with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SNAPSHOT_STALE"):
                load_announcement_snapshot(
                    h.store, task, UUID(previous["snapshot_id"]), h.principal
                )
        previous = materialize_announcement_snapshot(
            h.store, task, base, preview["dependencies_hash"], h.principal
        )


def test_concurrent_materialization_returns_one_record(harness: StoreHarness) -> None:
    h = harness
    task, base, _, _ = prepared(h)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: materialize_announcement_snapshot(
                    h.store, task, base, preview["dependencies_hash"], h.principal
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationAnnouncementSnapshot)))) == 1


@pytest.mark.parametrize("change", ["verifier", "permission", "raw-bytes", "parent-dependency"])
def test_cached_results_recheck_current_evidence_and_authority(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, base, source, _ = prepared(h)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    saved = materialize_announcement_snapshot(
        h.store, task, base, preview["dependencies_hash"], h.principal
    )
    if change == "verifier":
        monkeypatch.setattr(
            "deepaha.investigations.evidence_checks.VERIFIER_VERSION", "synthetic-next"
        )
    elif change == "permission":
        from deepaha.review.models import ReviewerAccountModel

        with h.factory.begin() as session:
            account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
            assert account is not None
            account.active = False
    elif change == "raw-bytes":
        from deepaha.artifacts.models import RawArtifact

        with h.factory() as session:
            raw = session.scalar(select(RawArtifact))
            assert raw is not None
            path = h.object_root / raw.storage_bucket / "objects" / raw.object_key
        path.write_bytes(b"Synthetic changed source, not the captured original")
    else:
        from deepaha.p9b.facts import FactLifecycleService
        from deepaha.p9b.models import VerifiedFactSetDependency

        with h.factory.begin() as session:
            prep = session.get(InvestigationRulePreparation, source)
            assert prep is not None
            dependency = session.scalar(
                select(VerifiedFactSetDependency).where(
                    VerifiedFactSetDependency.verified_fact_set_id == prep.fact_set_id
                )
            )
            assert dependency is not None
            FactLifecycleService(session).invalidate_dependency(
                verified_fact_set_id=prep.fact_set_id,
                dependency_id=dependency.dependency_id,
                observed_dependency_fingerprint="f" * 64,
                reason_code="SYNTHETIC_CHANGED_INPUT",
                actor_identity=f"human:{h.principal.reviewer_id}",
                created_at=h.clock(),
            )
    operations: tuple[Callable[[], dict[str, Any]], ...] = (
        lambda: preview_announcement_snapshot(h.store, task, base, h.principal),
        lambda: materialize_announcement_snapshot(
            h.store, task, base, preview["dependencies_hash"], h.principal
        ),
        lambda: load_announcement_snapshot(h.store, task, UUID(saved["snapshot_id"]), h.principal),
    )
    for operation in operations:
        with pytest.raises(InvestigationError):
            operation()


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_snapshot_is_append_only(harness: StoreHarness, operation: str) -> None:
    h = harness
    task, base, _, _ = prepared(h)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    materialize_announcement_snapshot(
        h.store, task, base, preview["dependencies_hash"], h.principal
    )
    sql = (
        "UPDATE investigation_announcement_snapshots SET created_at=now()"
        if operation == "UPDATE"
        else "DELETE FROM investigation_announcement_snapshots"
    )
    with (
        pytest.raises(DBAPIError, match="ANNOUNCEMENT_SNAPSHOT_IMMUTABLE"),
        h.factory.begin() as session,
    ):
        session.execute(text(sql))


def test_history_refuses_downgrade(harness: StoreHarness) -> None:
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    h = harness
    task, base, _, _ = prepared(h)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    materialize_announcement_snapshot(
        h.store, task, base, preview["dependencies_hash"], h.principal
    )
    migration = import_module("migrations.versions.20260909_0044_announcement_snapshots")
    with (
        h.factory.begin() as session,
        Operations.context(MigrationContext.configure(session.connection())),
        pytest.raises(RuntimeError, match="HISTORY_DOWNGRADE_REFUSED"),
    ):
        migration.downgrade()


def test_future_dated_announcement_fact_cannot_enter_inherited_snapshot(
    harness: StoreHarness,
) -> None:
    from datetime import timedelta

    from deepaha.p9b.models import ExtractionCandidate, FactVerificationDecisionModel

    h = harness

    def future(_mapper: Any, connection: Any, record: FactVerificationDecisionModel) -> None:
        scope = connection.scalar(
            select(ExtractionCandidate.target_scope).where(
                ExtractionCandidate.candidate_id == record.candidate_id
            )
        )
        if scope == "OPPORTUNITY":
            record.decided_at += timedelta(days=1)

    event.listen(FactVerificationDecisionModel, "before_insert", future)
    try:
        task, base, source, candidate = prepared(h)
    finally:
        event.remove(FactVerificationDecisionModel, "before_insert", future)
    view = read_rule_applicability(h.store, task, base, source, candidate, h.principal)
    save_rule_applicability(h.store, task, command(view), h.principal, "apply")
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SOURCE_FACT_ACTION_CONFLICT"):
        preview_announcement_snapshot(h.store, task, base, h.principal)


@pytest.mark.parametrize("attack", ["denominator", "rule", "target", "qualification"])
def test_sql_rejects_forged_scope_even_with_recomputed_hashes(
    harness: StoreHarness, attack: str
) -> None:
    h = harness
    task, base, source, candidate = prepared(h)
    view = read_rule_applicability(h.store, task, base, source, candidate, h.principal)
    save_rule_applicability(h.store, task, command(view), h.principal, "apply")
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)

    def corrupt(_mapper: Any, _connection: Any, record: InvestigationAnnouncementSnapshot) -> None:
        if attack == "denominator":
            record.snapshot["announcement_conditions"] = []
        elif attack == "rule":
            cast(list[dict[str, Any]], record.snapshot["announcement_conditions"])[0][
                "source_rule"
            ]["value"] = "PHD"
        elif attack == "target":
            record.unit_version_id = uuid7()
        else:
            record.snapshot["overall_qualification"] = "ELIGIBLE"
        record.snapshot_hash = digest(record.snapshot)

    event.listen(InvestigationAnnouncementSnapshot, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError):
            materialize_announcement_snapshot(
                h.store, task, base, preview["dependencies_hash"], h.principal
            )
    finally:
        event.remove(InvestigationAnnouncementSnapshot, "before_insert", corrupt)


def test_trusted_read_rebuilds_content_instead_of_trusting_self_hash(harness: StoreHarness) -> None:
    h = harness
    task, base, _, _ = prepared(h)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    snapshot = deepcopy(preview["snapshot"])
    snapshot["announcement_conditions"][0]["reasons"] = ["fabricated reason"]
    snapshot_id = uuid7()
    with h.factory.begin() as session:
        session.execute(
            insert(InvestigationAnnouncementSnapshot).values(
                snapshot_id=snapshot_id,
                base_plan_id=base,
                unit_version_id=UUID(snapshot["base_v2"]["plan"]["target"]["unit_version_id"]),
                contract_version=snapshot["contract_version"],
                adapter_version=snapshot["adapter_version"],
                dependencies=preview["dependencies"],
                dependencies_hash=preview["dependencies_hash"],
                snapshot=snapshot,
                snapshot_hash=digest(snapshot),
                reviewer_id=h.principal.reviewer_id,
                created_at=h.clock(),
            )
        )
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SNAPSHOT_INTEGRITY_FAILED"):
        load_announcement_snapshot(h.store, task, snapshot_id, h.principal)
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SNAPSHOT_INTEGRITY_FAILED"):
        materialize_announcement_snapshot(
            h.store, task, base, preview["dependencies_hash"], h.principal
        )


@pytest.mark.parametrize("attack", ["text", "reference", "omit-row"])
def test_source_rule_preparation_rebuild_rejects_rehashed_changes(
    harness: StoreHarness, attack: str
) -> None:
    h = harness
    task, base, source, _ = prepared(h)
    preview = preview_announcement_snapshot(h.store, task, base, h.principal)
    saved = materialize_announcement_snapshot(
        h.store, task, base, preview["dependencies_hash"], h.principal
    )

    def corrupt(record: InvestigationRulePreparation, _context: Any) -> None:
        if record.rule_preparation_id != source:
            return
        rows = cast(list[dict[str, Any]], record.result["rows"])
        if attack == "text":
            rows[0]["evidence"][0]["text"] = "Synthetic invented evidence text"
        elif attack == "reference":
            rows[0]["evidence_ref_ids"] = [str(uuid7())]
        else:
            record.result["rows"] = []
        record.result_hash = digest(record.result)

    # Corrupt the loaded source representation without disabling immutable SQL guards.
    event.listen(InvestigationRulePreparation, "load", corrupt)
    try:
        with pytest.raises(InvestigationError):
            preview_announcement_snapshot(h.store, task, base, h.principal)
        with pytest.raises(InvestigationError):
            load_announcement_snapshot(h.store, task, UUID(saved["snapshot_id"]), h.principal)
    finally:
        event.remove(InvestigationRulePreparation, "load", corrupt)


def test_private_http_lifecycle_stale_forbidden_and_cross_task(harness: StoreHarness) -> None:
    from fastapi import FastAPI

    from deepaha.api.investigations import get_investigation_store
    from deepaha.api.local_human_test import require_local_test_principal
    from deepaha.review.models import ReviewerAccountModel
    from tests.api.test_investigations import make_client

    h = harness
    task, base, source, candidate = prepared(h)
    client, _ = make_client(h.object_root)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    root = f"/api/v1/local-human-test/investigations/{task}"
    path = f"{root}/unit-plans/{base}"
    with client:
        initial = client.get(path + "/announcement-snapshot-input")
        assert (
            initial.status_code == 200 and initial.headers["cache-control"] == "private, no-store"
        )
        body = {"expected_dependencies_hash": initial.json()["dependencies_hash"]}
        saved = client.post(path + "/announcement-snapshots", json=body)
        assert saved.status_code == 200
        assert client.post(path + "/announcement-snapshots", json=body).json() == saved.json()
        read_path = root + "/announcement-snapshots/" + saved.json()["snapshot_id"]
        assert client.get(read_path).json() == saved.json()
        foreign = client.get(read_path.replace(str(task), str(uuid7())))
        assert foreign.status_code == 404 and "snapshot" not in foreign.json()
        view = read_rule_applicability(h.store, task, base, source, candidate, h.principal)
        save_rule_applicability(h.store, task, command(view), h.principal, "http-change")
        assert client.get(read_path).status_code == 409
        assert client.post(path + "/announcement-snapshots", json=body).status_code == 409
        with h.factory.begin() as session:
            account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
            assert account is not None
            account.active = False
        forbidden = client.get(path + "/announcement-snapshot-input")
        assert (
            forbidden.status_code == 403
            and forbidden.headers["cache-control"] == "private, no-store"
        )
        assert "snapshot" not in forbidden.json()
