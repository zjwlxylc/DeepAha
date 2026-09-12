"""Integration checks for persistent dispatch intent; synthetic fixtures only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.investigations.contracts import CreateInvestigation, InvestigationError
from deepaha.investigations.models import InvestigationEvent, InvestigationTask
from deepaha.investigations.store import InvestigationStore
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
)
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import Source, SourceEndpoint

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 11, 8, tzinfo=UTC)
BUCKET = "investigation-dispatch-tests"


@dataclass
class MutableClock:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value


@dataclass
class DispatchHarness:
    store: InvestigationStore
    factory: sessionmaker[Session]
    objects: LocalFileObjectStore
    clock: MutableClock
    command: CreateInvestigation
    principal: ReviewerPrincipal


@pytest.fixture
def harness(migrated_engine: Engine, tmp_path: Path) -> DispatchHarness:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    source_id, endpoint_id, reviewer_id = uuid7(), uuid7(), uuid7()
    roles = frozenset({ReviewerRole.LOCAL_TEST_OPERATOR, ReviewerRole.VALIDATION_REVIEWER})
    principal = ReviewerPrincipal(
        reviewer_id, roles, frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}), False
    )
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id=f"src_{source_id.hex}",
                canonical_url="https://example.gov/",
                authority_name="Synthetic issuer",
                tier="OFFICIAL_PRIMARY",
                jurisdiction="Synthetic region",
                active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            ReviewerAccountModel(
                reviewer_id=reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"test-only-reviewer-{reviewer_id.hex}",
                roles=[role.value for role in roles],
                allowed_purposes=[OPPORTUNITY_FACT_VALIDATION_PURPOSE],
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            SourceEndpoint(
                endpoint_id=endpoint_id,
                source_id=source_id,
                url="https://example.gov/notice",
                allowed_hosts=["example.gov"],
                expected_media_types=["text/html"],
                browser_policy="NEVER",
                minimum_interval_seconds=1,
                timeout_seconds=5,
                max_attempts=1,
                robots_url=None,
                robots_decision="ALLOWED",
                robots_checked_at=NOW,
                content_use_basis="OFFICIAL_PUBLIC_ACCESS",
                license_name=None,
                license_url=None,
                attribution=None,
                fixture_storage_allowed=False,
                usage_note="Synthetic bytes only; no real site or human acceptance evidence.",
                policy_version="synthetic-policy-1",
                active=True,
                verified_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    objects = LocalFileObjectStore(root=tmp_path, bucket=BUCKET)
    objects.ensure_bucket()
    clock = MutableClock()
    command = CreateInvestigation(
        source_id=source_id,
        endpoint_id=endpoint_id,
        notice_url="https://example.gov/notice",
        brief="Investigate only the supplied synthetic notice.",
        expected_entity_keys=("position",),
        wall_time_seconds=60,
    )
    return DispatchHarness(
        InvestigationStore(factory, objects, clock),
        factory,
        objects,
        clock,
        command,
        principal,
    )


def _event_count(session: Session, task_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(InvestigationEvent)
            .where(InvestigationEvent.task_id == task_id)
        )
        or 0
    )


def _recovery_task(h: DispatchHarness, key: str, status: str) -> tuple[UUID, UUID]:
    """Drive a task into a resumable state carrying both remote identifiers.

    Returns the task id and the lease owner so the caller can either release the
    lease with ``fail`` or leave it live.
    """
    task_id = h.store.create(h.command, h.principal, key)
    owner = uuid7()
    h.store.claim(task_id, owner, {"provider": "SYNTHETIC_TEST"})
    h.store.transition(task_id, owner, "PREPARING", ("synthetic-runtime", f"session-{key}"))
    h.store.transition(task_id, owner, "INVESTIGATING")
    if status == "COLLECTING":
        h.store.transition(task_id, owner, "COLLECTING")
    return task_id, owner


def test_request_dispatch_is_idempotent_and_writes_intent_once(harness: DispatchHarness) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "dispatch-intent")
    with h.factory() as session:
        before = _event_count(session, task_id)
    first = h.store.request_dispatch(task_id, h.principal)
    second = h.store.request_dispatch(task_id, h.principal)
    assert first["status"] == second["status"] == "QUEUED"
    assert first["dispatch_requested_at"] is not None
    assert first["dispatch_requested_at"] == second["dispatch_requested_at"]
    h.clock.value += timedelta(seconds=30)
    third = h.store.request_dispatch(task_id, h.principal)
    assert third["dispatch_requested_at"] == first["dispatch_requested_at"]
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and task.dispatch_requested_at is not None
        assert _event_count(session, task_id) == before


def test_request_dispatch_requires_a_queued_task_with_a_free_lease(
    harness: DispatchHarness,
) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "guarded")
    owner = uuid7()
    h.store.claim(task_id, owner, {"provider": "SYNTHETIC_TEST"})
    with pytest.raises(InvestigationError, match="TASK_NOT_DISPATCHABLE"):
        h.store.request_dispatch(task_id, h.principal)
    # A queued task that still holds a live lease is reported distinctly.
    with h.factory.begin() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None
        task.status = "QUEUED"
    with pytest.raises(InvestigationError, match="TASK_ALREADY_RUNNING"):
        h.store.request_dispatch(task_id, h.principal)


def test_request_dispatch_rejects_synthetic_and_unauthorized_operators(
    harness: DispatchHarness,
) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "authority")
    with pytest.raises(InvestigationError, match="REAL_OPERATOR_REQUIRED"):
        h.store.request_dispatch(task_id, replace(h.principal, synthetic=True))
    unrelated = ReviewerPrincipal(
        uuid7(),
        frozenset({ReviewerRole.FEEDBACK_REVIEWER}),
        frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        False,
    )
    with pytest.raises(ReviewerAuthenticationError):
        h.store.request_dispatch(task_id, unrelated)
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and task.dispatch_requested_at is None


def test_list_dispatchable_separates_kinds_and_hides_busy_leases(
    harness: DispatchHarness,
) -> None:
    h = harness
    new_id = h.store.create(h.command, h.principal, "new-intent")
    h.store.request_dispatch(new_id, h.principal)
    plain_id = h.store.create(h.command, h.principal, "no-intent")

    recover_id, owner = _recovery_task(h, "recoverable", "COLLECTING")
    h.store.fail(recover_id, owner, "COLLECTION_RETRYABLE", "SYNTHETIC_DOWNLOAD_FAILED")

    incomplete_id = h.store.create(h.command, h.principal, "incomplete")
    owner2 = uuid7()
    h.store.claim(incomplete_id, owner2, {"provider": "SYNTHETIC_TEST"})
    h.store.transition(incomplete_id, owner2, "PREPARING", ("synthetic-runtime", None))
    h.store.transition(incomplete_id, owner2, "INVESTIGATING")
    h.store.fail(incomplete_id, owner2, "EXECUTION_UNCERTAIN", "SYNTHETIC_UNCERTAIN")

    busy_id, _busy_owner = _recovery_task(h, "busy", "COLLECTING")

    listed = {row["task_id"]: row for row in h.store.list_dispatchable(h.clock())}
    assert listed[new_id]["kind"] == "NEW"
    assert listed[new_id]["created_by"] == h.principal.reviewer_id
    assert recover_id not in listed  # historical tasks require explicit recovery intent
    assert plain_id not in listed  # no persistent intent is never auto-dispatched
    assert incomplete_id not in listed  # EXECUTION_UNCERTAIN without a session (#7)
    assert busy_id not in listed  # a live lease is not stolen

    h.clock.value += timedelta(seconds=70)
    assert busy_id not in {row["task_id"] for row in h.store.list_dispatchable(h.clock())}


def test_restart_rediscovers_an_existing_recovery_candidate(harness: DispatchHarness) -> None:
    h = harness
    recover_id, owner = _recovery_task(h, "restart", "COLLECTING")
    h.store.fail(recover_id, owner, "COLLECTION_RETRYABLE", "SYNTHETIC_DOWNLOAD_FAILED")
    h.store.request_dispatch(recover_id, h.principal, configuration_revision=str(uuid7()))
    restarted = InvestigationStore(h.factory, h.objects, h.clock)
    assert recover_id in {row["task_id"] for row in restarted.list_dispatchable(h.clock())}


def test_cancel_dispatch_clears_intent_records_code_and_preserves_lease_columns(
    harness: DispatchHarness,
) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "cancellable")
    h.store.request_dispatch(task_id, h.principal)
    h.store.cancel_dispatch(task_id, "WMA_RELEASE_INSPECTION_FAILED")
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None
        assert task.dispatch_requested_at is None
        assert task.status == "QUEUED"
        assert task.error_code == "WMA_RELEASE_INSPECTION_FAILED"
        assert task.lease_owner is None and task.lease_until is None
        events = list(
            session.scalars(
                select(InvestigationEvent)
                .where(InvestigationEvent.task_id == task_id)
                .order_by(InvestigationEvent.sequence)
            )
        )
        assert events[-1].status == "QUEUED"
        assert events[-1].error_code == "WMA_RELEASE_INSPECTION_FAILED"
        count = len(events)

    h.store.cancel_dispatch(task_id, "WMA_RELEASE_INSPECTION_FAILED")
    with h.factory() as session:
        assert _event_count(session, task_id) == count
    assert task_id not in {row["task_id"] for row in h.store.list_dispatchable(h.clock())}

    repeated = h.store.request_dispatch(task_id, h.principal)
    assert repeated["dispatch_requested_at"] is not None
    kinds = {row["task_id"]: row["kind"] for row in h.store.list_dispatchable(h.clock())}
    assert kinds[task_id] == "NEW"


def test_concurrent_request_dispatch_serializes_to_one_intent(harness: DispatchHarness) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "concurrent-intent")
    with h.factory() as session:
        before = _event_count(session, task_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        views = list(pool.map(lambda _: h.store.request_dispatch(task_id, h.principal), range(2)))
    assert views[0]["dispatch_requested_at"] == views[1]["dispatch_requested_at"]
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and task.dispatch_requested_at is not None
        assert _event_count(session, task_id) == before


def test_dispatch_pins_configuration_and_retains_intent_after_claim(
    harness: DispatchHarness,
) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "pinned-configuration")
    revision = str(uuid7())
    h.store.request_dispatch(task_id, h.principal, configuration_revision=revision)
    h.store.request_dispatch(task_id, h.principal, configuration_revision=str(uuid7()))
    intent = h.store.list_dispatchable(h.clock())[0]["dispatch_intent"]
    assert intent["configuration_revision"] == revision
    assert intent["operator_id"] == str(h.principal.reviewer_id)
    h.store.claim(task_id, uuid7(), {"provider": "SYNTHETIC_TEST"})
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and task.dispatch_context == intent


def test_old_remote_task_is_not_automatically_recovered(harness: DispatchHarness) -> None:
    h = harness
    task_id, owner = _recovery_task(h, "old-remote-task", "COLLECTING")
    h.store.fail(task_id, owner, "COLLECTION_RETRYABLE", "SYNTHETIC_DOWNLOAD_FAILED")
    assert task_id not in {row["task_id"] for row in h.store.list_dispatchable(h.clock())}


def test_explicit_recovery_is_durable_and_finished_attempt_needs_a_new_request(
    harness: DispatchHarness,
) -> None:
    h = harness
    task_id, owner = _recovery_task(h, "explicit-recovery", "COLLECTING")
    h.store.fail(task_id, owner, "COLLECTION_RETRYABLE", "SYNTHETIC_DOWNLOAD_FAILED")
    revision = str(uuid7())
    h.store.request_dispatch(
        task_id, h.principal, configuration_revision=revision, request_key="recovery-once"
    )
    candidate = h.store.list_dispatchable(h.clock())[0]
    assert candidate["kind"] == "RECOVER"
    h.store.finish_dispatch(task_id, candidate["dispatch_intent"]["intent_id"])
    assert h.store.list_dispatchable(h.clock()) == []
    h.store.request_dispatch(
        task_id, h.principal, configuration_revision=revision, request_key="recovery-once"
    )
    assert h.store.list_dispatchable(h.clock()) == []
    h.store.request_dispatch(
        task_id, h.principal, configuration_revision=revision, request_key="recovery-again"
    )
    assert len(h.store.list_dispatchable(h.clock())) == 1


def test_losing_worker_cannot_finish_an_active_dispatch(harness: DispatchHarness) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "active-dispatch")
    h.store.request_dispatch(task_id, h.principal, configuration_revision=str(uuid7()))
    intent_id = h.store.list_dispatchable(h.clock())[0]["dispatch_intent"]["intent_id"]
    h.store.claim(task_id, uuid7(), {"provider": "SYNTHETIC_TEST"})
    h.store.finish_dispatch(task_id, intent_id)
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and "finished_at" not in task.dispatch_context
