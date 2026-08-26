from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import exists, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.local_human_test.contracts import CreateRunCommand, ItemStatus, RunStatus
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.p9b.hashing import canonical_json_bytes

LEASE_SECONDS = 60
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_WORKER_ITEM_STATUSES = frozenset(
    {
        ItemStatus.CREATED,
        ItemStatus.ACQUIRING,
        ItemStatus.EXTRACTING,
    }
)
_TERMINAL_ITEM_STATUSES = frozenset(
    {
        ItemStatus.COMPLETED,
        ItemStatus.ACQUISITION_REJECTED,
        ItemStatus.FAILED_CONFIG,
        ItemStatus.PARTIAL_BUDGET_EXHAUSTED,
        ItemStatus.MODEL_OUTPUT_INVALID,
        ItemStatus.EVIDENCE_BINDING_INVALID,
        ItemStatus.FAILED,
        ItemStatus.CANCELLED,
    }
)
_ERROR_ITEM_STATUSES = _TERMINAL_ITEM_STATUSES - {ItemStatus.COMPLETED}

_ALLOWED_TRANSITIONS: Mapping[ItemStatus, frozenset[ItemStatus]] = {
    ItemStatus.CREATED: frozenset(
        {
            ItemStatus.ACQUIRING,
            ItemStatus.FAILED_CONFIG,
            ItemStatus.FAILED,
            ItemStatus.CANCELLED,
        }
    ),
    ItemStatus.ACQUIRING: frozenset(
        {
            ItemStatus.BOOTSTRAP_REVIEW,
            ItemStatus.EXTRACTING,
            ItemStatus.ACQUISITION_REJECTED,
            ItemStatus.PARTIAL_BUDGET_EXHAUSTED,
            ItemStatus.FAILED,
            ItemStatus.CANCELLED,
        }
    ),
    ItemStatus.BOOTSTRAP_REVIEW: frozenset(
        {
            ItemStatus.EXTRACTING,
            ItemStatus.ACQUISITION_REJECTED,
            ItemStatus.FAILED,
            ItemStatus.CANCELLED,
        }
    ),
    ItemStatus.EXTRACTING: frozenset(
        {
            ItemStatus.FACT_REVIEW,
            ItemStatus.PARTIAL_BUDGET_EXHAUSTED,
            ItemStatus.UNKNOWN_OUTCOME,
            ItemStatus.MODEL_OUTPUT_INVALID,
            ItemStatus.EVIDENCE_BINDING_INVALID,
            ItemStatus.FAILED_CONFIG,
            ItemStatus.FAILED,
            ItemStatus.CANCELLED,
        }
    ),
    ItemStatus.FACT_REVIEW: frozenset(
        {ItemStatus.RULE_REVIEW, ItemStatus.FAILED, ItemStatus.CANCELLED}
    ),
    ItemStatus.RULE_REVIEW: frozenset(
        {ItemStatus.READY_TO_PUBLISH, ItemStatus.FAILED, ItemStatus.CANCELLED}
    ),
    ItemStatus.READY_TO_PUBLISH: frozenset(
        {ItemStatus.COMPLETED, ItemStatus.FAILED, ItemStatus.CANCELLED}
    ),
    ItemStatus.UNKNOWN_OUTCOME: frozenset({ItemStatus.CANCELLED}),
}


class HumanTestRunError(ValueError):
    pass


class RunIdempotencyConflict(HumanTestRunError):
    pass


class RunNotFound(HumanTestRunError):
    pass


class ItemNotFound(HumanTestRunError):
    pass


class ItemTransitionError(HumanTestRunError):
    pass


class BudgetExhausted(HumanTestRunError):
    pass


class LeaseConflict(HumanTestRunError):
    pass


@dataclass(frozen=True, slots=True)
class RunClaim:
    run_id: UUID
    item_id: UUID
    recipe_id: str
    lease_owner: str
    lease_expires_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("time must be timezone-aware")
    return value


def _validate_identity(value: str, *, label: str) -> str:
    if not 1 <= len(value) <= 128 or value != value.strip():
        raise ValueError(f"{label} must be 1..128 characters without outer whitespace")
    if any(not character.isprintable() for character in value):
        raise ValueError(f"{label} must contain printable characters only")
    return value


def create_run_request_hash(command: CreateRunCommand) -> str:
    payload = command.model_dump(mode="json")
    domain = b"deepaha:local-human-test:create-run:v1\0"
    return sha256(domain + canonical_json_bytes(payload)).hexdigest()


def assert_item_transition(current: ItemStatus | str, target: ItemStatus | str) -> None:
    current_value = ItemStatus(current)
    target_value = ItemStatus(target)
    if target_value not in _ALLOWED_TRANSITIONS.get(current_value, frozenset()):
        raise ItemTransitionError(
            f"ITEM_TRANSITION_FORBIDDEN:{current_value.value}->{target_value.value}"
        )


def reserve_budget_count(current: int, *, limit: int, kind: str) -> int:
    if kind not in {"official_request", "llm_call"}:
        raise ValueError("unknown budget kind")
    if current < 0 or limit < 1:
        raise ValueError("budget counters must be non-negative and limits positive")
    if current >= limit:
        code = (
            "OFFICIAL_REQUEST_BUDGET_EXHAUSTED"
            if kind == "official_request"
            else "LLM_CALL_BUDGET_EXHAUSTED"
        )
        raise BudgetExhausted(code)
    return current + 1


def derive_terminal_run_status(statuses: Iterable[ItemStatus | str]) -> RunStatus:
    resolved = tuple(ItemStatus(status) for status in statuses)
    if not resolved or any(status not in _TERMINAL_ITEM_STATUSES for status in resolved):
        raise ItemTransitionError("RUN_HAS_NONTERMINAL_ITEMS")
    if all(status is ItemStatus.COMPLETED for status in resolved):
        return RunStatus.COMPLETED
    if all(status is ItemStatus.CANCELLED for status in resolved):
        return RunStatus.CANCELLED
    if any(status is ItemStatus.PARTIAL_BUDGET_EXHAUSTED for status in resolved):
        return RunStatus.PARTIAL
    if any(status is ItemStatus.COMPLETED for status in resolved):
        return RunStatus.PARTIAL
    return RunStatus.FAILED


class HumanTestRunService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        now_factory: Callable[[], datetime] = _utc_now,
        lease_seconds: int = LEASE_SECONDS,
    ) -> None:
        if lease_seconds != LEASE_SECONDS:
            raise ValueError("local human-test lease must be exactly 60 seconds")
        self._session_factory = session_factory
        self._now_factory = now_factory
        self._lease_seconds = lease_seconds

    def create(
        self,
        command: CreateRunCommand,
        *,
        idempotency_key: str,
    ) -> LocalHumanTestRun:
        key = _validate_identity(idempotency_key, label="idempotency key")
        request_hash = create_run_request_hash(command)
        now = _require_aware(self._now_factory())
        lock_identity = f"{command.reviewer_id}:{key}"
        with self._session_factory.begin() as session:
            session.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": lock_identity},
            )
            existing = session.scalar(
                select(LocalHumanTestRun).where(
                    LocalHumanTestRun.created_by_reviewer_id == command.reviewer_id,
                    LocalHumanTestRun.idempotency_key == key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise RunIdempotencyConflict("RUN_CREATE_IDEMPOTENCY_CONFLICT")
                return existing

            run = LocalHumanTestRun(
                mode=command.mode.value,
                recipe_ids=list(command.recipe_ids),
                provider_config_snapshot=command.provider.model_dump(mode="json"),
                budget=command.budget.model_dump(mode="json"),
                status=RunStatus.CREATED.value,
                official_request_count=0,
                llm_call_count=0,
                created_by_reviewer_id=command.reviewer_id,
                idempotency_key=key,
                request_hash=request_hash,
                lease_owner=None,
                lease_expires_at=None,
                terminal_reason_code=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
            session.add(run)
            session.flush()
            session.add_all(
                LocalHumanTestItem(
                    run_id=run.run_id,
                    recipe_id=recipe_id,
                    source_id=None,
                    endpoint_id=None,
                    acquisition_evaluation_id=None,
                    document_id=None,
                    opportunity_id=None,
                    source_bundle_revision_id=None,
                    extraction_run_id=None,
                    model_call_id=None,
                    verified_fact_set_id=None,
                    status=ItemStatus.CREATED.value,
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                for recipe_id in command.recipe_ids
            )
            session.flush()
            return run

    def request_cancel(self, run_id: UUID) -> LocalHumanTestRun:
        now = _require_aware(self._now_factory())
        with self._session_factory.begin() as session:
            run = self._locked_run(session, run_id)
            current = RunStatus(run.status)
            if current is RunStatus.CANCELLED:
                return run
            if current in {RunStatus.COMPLETED, RunStatus.PARTIAL, RunStatus.FAILED}:
                raise ItemTransitionError("TERMINAL_RUN_CANNOT_BE_CANCELLED")
            items = session.scalars(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.run_id == run_id)
                .with_for_update()
            ).all()
            for item in items:
                if ItemStatus(item.status) not in _TERMINAL_ITEM_STATUSES:
                    item.status = ItemStatus.CANCELLED.value
                    item.error_code = "USER_CANCELLED"
                    item.updated_at = now
            run.status = RunStatus.CANCELLED.value
            run.terminal_reason_code = "USER_CANCELLED"
            run.completed_at = now
            run.updated_at = now
            self._clear_lease(run)
            session.flush()
            return run

    def claim_next(self, worker_id: str, now: datetime | None = None) -> RunClaim | None:
        owner = _validate_identity(worker_id, label="worker ID")
        current_time = _require_aware(now or self._now_factory())
        worker_statuses = tuple(status.value for status in _WORKER_ITEM_STATUSES)
        claimable_item = exists(
            select(LocalHumanTestItem.item_id).where(
                LocalHumanTestItem.run_id == LocalHumanTestRun.run_id,
                LocalHumanTestItem.status.in_(worker_statuses),
            )
        )
        with self._session_factory.begin() as session:
            run = session.scalar(
                select(LocalHumanTestRun)
                .where(
                    LocalHumanTestRun.status.in_(
                        (RunStatus.CREATED.value, RunStatus.RUNNING.value)
                    ),
                    or_(
                        LocalHumanTestRun.lease_owner.is_(None),
                        LocalHumanTestRun.lease_expires_at <= current_time,
                    ),
                    claimable_item,
                )
                .order_by(LocalHumanTestRun.created_at, LocalHumanTestRun.run_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if run is None:
                return None
            item = session.scalar(
                select(LocalHumanTestItem)
                .where(
                    LocalHumanTestItem.run_id == run.run_id,
                    LocalHumanTestItem.status.in_(worker_statuses),
                )
                .order_by(LocalHumanTestItem.created_at, LocalHumanTestItem.item_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if item is None:
                return None
            lease_expires_at = current_time + timedelta(seconds=self._lease_seconds)
            run.status = RunStatus.RUNNING.value
            run.lease_owner = owner
            run.lease_expires_at = lease_expires_at
            run.updated_at = current_time
            session.flush()
            return RunClaim(
                run_id=run.run_id,
                item_id=item.item_id,
                recipe_id=item.recipe_id,
                lease_owner=owner,
                lease_expires_at=lease_expires_at,
            )

    def renew_lease(
        self,
        run_id: UUID,
        worker_id: str,
        *,
        now: datetime | None = None,
    ) -> datetime:
        owner = _validate_identity(worker_id, label="worker ID")
        current_time = _require_aware(now or self._now_factory())
        with self._session_factory.begin() as session:
            run = self._locked_run(session, run_id)
            self._require_active_lease(run, owner, current_time)
            expires_at = current_time + timedelta(seconds=self._lease_seconds)
            run.lease_expires_at = expires_at
            run.updated_at = current_time
            session.flush()
            return expires_at

    def release_lease(
        self,
        run_id: UUID,
        worker_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        owner = _validate_identity(worker_id, label="worker ID")
        current_time = _require_aware(now or self._now_factory())
        with self._session_factory.begin() as session:
            run = self._locked_run(session, run_id)
            if run.lease_owner != owner:
                raise LeaseConflict("RUN_LEASE_OWNER_MISMATCH")
            self._clear_lease(run)
            run.updated_at = current_time

    def record_official_request(self, run_id: UUID, worker_id: str) -> int:
        return self._reserve_external_call(run_id, worker_id, kind="official_request")

    def record_llm_call(self, run_id: UUID, worker_id: str) -> int:
        return self._reserve_external_call(run_id, worker_id, kind="llm_call")

    def record_item_llm_call(
        self,
        item_id: UUID,
        model_call_id: UUID,
        worker_id: str,
    ) -> int:
        """Bind one registered ModelCall and one budget unit atomically to an item."""
        owner = _validate_identity(worker_id, label="worker ID")
        now = _require_aware(self._now_factory())
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.item_id == item_id)
                .with_for_update()
            )
            if item is None:
                raise ItemNotFound("LOCAL_HUMAN_TEST_ITEM_NOT_FOUND")
            run = self._locked_run(session, item.run_id)
            self._require_active_lease(run, owner, now)
            if ItemStatus(item.status) is not ItemStatus.EXTRACTING:
                raise ItemTransitionError("ITEM_NOT_EXTRACTING")
            if item.model_call_id is not None:
                if item.model_call_id != model_call_id:
                    raise ItemTransitionError("ITEM_MODEL_CALL_IMMUTABLE")
                return run.llm_call_count
            limit = self._budget_limit(run, "llm_call_limit")
            run.llm_call_count = reserve_budget_count(
                run.llm_call_count,
                limit=limit,
                kind="llm_call",
            )
            item.model_call_id = model_call_id
            item.updated_at = now
            run.updated_at = now
            session.flush()
            return run.llm_call_count

    def transition_item(
        self,
        item_id: UUID,
        *,
        expected: ItemStatus,
        target: ItemStatus,
        error_code: str | None = None,
        references: Mapping[str, UUID | None] | None = None,
        now: datetime | None = None,
    ) -> LocalHumanTestItem:
        assert_item_transition(expected, target)
        if target in _ERROR_ITEM_STATUSES or target is ItemStatus.UNKNOWN_OUTCOME:
            if error_code is None or _ERROR_CODE.fullmatch(error_code) is None:
                raise ItemTransitionError("ITEM_ERROR_CODE_REQUIRED")
        elif error_code is not None:
            raise ItemTransitionError("ITEM_ERROR_CODE_FORBIDDEN")
        current_time = _require_aware(now or self._now_factory())
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.item_id == item_id)
                .with_for_update()
            )
            if item is None:
                raise ItemNotFound("LOCAL_HUMAN_TEST_ITEM_NOT_FOUND")
            if ItemStatus(item.status) is not expected:
                raise ItemTransitionError("ITEM_STATE_CHANGED")
            if references:
                self._apply_references(item, references)
            item.status = target.value
            item.error_code = error_code
            item.updated_at = current_time
            session.flush()
            return item

    def complete_run(self, run_id: UUID) -> LocalHumanTestRun:
        now = _require_aware(self._now_factory())
        with self._session_factory.begin() as session:
            run = self._locked_run(session, run_id)
            statuses = session.scalars(
                select(LocalHumanTestItem.status)
                .where(LocalHumanTestItem.run_id == run_id)
                .order_by(LocalHumanTestItem.item_id)
                .with_for_update()
            ).all()
            terminal = derive_terminal_run_status(statuses)
            run.status = terminal.value
            run.completed_at = run.completed_at or now
            run.updated_at = now
            if terminal is RunStatus.CANCELLED:
                run.terminal_reason_code = run.terminal_reason_code or "USER_CANCELLED"
            elif terminal is RunStatus.FAILED:
                run.terminal_reason_code = run.terminal_reason_code or "ALL_ITEMS_FAILED"
            elif terminal is RunStatus.PARTIAL:
                run.terminal_reason_code = run.terminal_reason_code or "PARTIAL_COMPLETION"
            else:
                run.terminal_reason_code = None
            self._clear_lease(run)
            session.flush()
            return run

    def _reserve_external_call(self, run_id: UUID, worker_id: str, *, kind: str) -> int:
        owner = _validate_identity(worker_id, label="worker ID")
        now = _require_aware(self._now_factory())
        with self._session_factory.begin() as session:
            run = self._locked_run(session, run_id)
            self._require_active_lease(run, owner, now)
            if kind == "official_request":
                limit = self._budget_limit(run, "official_request_limit")
                next_count = reserve_budget_count(
                    run.official_request_count,
                    limit=limit,
                    kind=kind,
                )
                run.official_request_count = next_count
            else:
                limit = self._budget_limit(run, "llm_call_limit")
                next_count = reserve_budget_count(run.llm_call_count, limit=limit, kind=kind)
                run.llm_call_count = next_count
            run.updated_at = now
            session.flush()
            return next_count

    @staticmethod
    def _budget_limit(run: LocalHumanTestRun, key: str) -> int:
        value = run.budget.get(key)
        if type(value) is not int:
            raise HumanTestRunError("RUN_BUDGET_SNAPSHOT_INVALID")
        return value

    @staticmethod
    def _locked_run(session: Session, run_id: UUID) -> LocalHumanTestRun:
        run = session.scalar(
            select(LocalHumanTestRun).where(LocalHumanTestRun.run_id == run_id).with_for_update()
        )
        if run is None:
            raise RunNotFound("LOCAL_HUMAN_TEST_RUN_NOT_FOUND")
        return run

    @staticmethod
    def _require_active_lease(
        run: LocalHumanTestRun,
        worker_id: str,
        now: datetime,
    ) -> None:
        if (
            run.lease_owner != worker_id
            or run.lease_expires_at is None
            or run.lease_expires_at <= now
        ):
            raise LeaseConflict("RUN_LEASE_NOT_ACTIVE")

    @staticmethod
    def _clear_lease(run: LocalHumanTestRun) -> None:
        run.lease_owner = None
        run.lease_expires_at = None

    @staticmethod
    def _apply_references(
        item: LocalHumanTestItem,
        references: Mapping[str, UUID | None],
    ) -> None:
        allowed = {
            "source_id",
            "endpoint_id",
            "acquisition_evaluation_id",
            "document_id",
            "opportunity_id",
            "source_bundle_revision_id",
            "extraction_run_id",
            "model_call_id",
            "verified_fact_set_id",
        }
        unknown = set(references) - allowed
        if unknown:
            raise ItemTransitionError("ITEM_REFERENCE_FIELD_UNKNOWN")
        for name, value in references.items():
            existing = getattr(item, name)
            if existing is not None and existing != value:
                raise ItemTransitionError("ITEM_REFERENCE_IMMUTABLE")
            setattr(item, name, value)


__all__ = [
    "BudgetExhausted",
    "HumanTestRunError",
    "HumanTestRunService",
    "ItemNotFound",
    "ItemTransitionError",
    "LEASE_SECONDS",
    "LeaseConflict",
    "RunClaim",
    "RunIdempotencyConflict",
    "RunNotFound",
    "assert_item_transition",
    "create_run_request_hash",
    "derive_terminal_run_status",
    "reserve_budget_count",
]
