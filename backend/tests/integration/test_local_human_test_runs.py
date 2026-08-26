import os
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from deepaha.local_human_test.contracts import (
    CreateRunCommand,
    ExternalCallBudget,
    ItemStatus,
    ProviderConfigSnapshot,
    RunMode,
    RunStatus,
)
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.runs import (
    BudgetExhausted,
    HumanTestRunService,
    ItemTransitionError,
    LeaseConflict,
    RunClaim,
    RunIdempotencyConflict,
)
from deepaha.local_human_test.worker import HumanTestWorker
from deepaha.review.models import ReviewerAccountModel

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)


def _temporary_database(database_url: str) -> tuple[str, Engine, URL, str]:
    database_name = f"deepaha_human_run_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_human_run_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    temporary_url = url.set(database=database_name)
    return (
        database_name,
        maintenance_engine,
        temporary_url,
        temporary_url.render_as_string(hide_password=False),
    )


@pytest.fixture(scope="module")
def human_test_engine(database_url: str) -> Iterator[Engine]:
    name, maintenance, temporary_url, rendered = _temporary_database(database_url)
    previous = os.environ.get("DEEPAHA_DATABASE_URL")
    engine: Engine | None = None
    try:
        os.environ["DEEPAHA_DATABASE_URL"] = rendered
        command.upgrade(Config("alembic.ini"), "head")
        engine = create_engine(temporary_url)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if previous is None:
            os.environ.pop("DEEPAHA_DATABASE_URL", None)
        else:
            os.environ["DEEPAHA_DATABASE_URL"] = previous
        with maintenance.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        maintenance.dispose()


@pytest.fixture
def factory(human_test_engine: Engine) -> Iterator[sessionmaker[Session]]:
    value = sessionmaker(bind=human_test_engine, expire_on_commit=False)
    reviewer_id = uuid7()
    with value.begin() as session:
        session.add(
            ReviewerAccountModel(
                reviewer_id=reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"local-operator-{reviewer_id}",
                roles=["LOCAL_TEST_OPERATOR"],
                allowed_purposes=["OPPORTUNITY_FACT_VALIDATION"],
                created_at=NOW,
            )
        )
    value.info = {"reviewer_id": reviewer_id}  # type: ignore[attr-defined]
    try:
        yield value
    finally:
        with value.begin() as session:
            session.query(LocalHumanTestRun).filter_by(created_by_reviewer_id=reviewer_id).delete()
            session.query(ReviewerAccountModel).filter_by(reviewer_id=reviewer_id).delete()


def _reviewer_id(factory: sessionmaker[Session]) -> UUID:
    return factory.info["reviewer_id"]  # type: ignore[attr-defined,no-any-return]


def _command(
    factory: sessionmaker[Session],
    *,
    recipes: tuple[str, ...] = ("zj-policy", "central-service"),
    model_id: str = "deepseek-chat",
) -> CreateRunCommand:
    provider = ProviderConfigSnapshot.model_validate(
        {
            "provider": "deepseek",
            "base_url": "https://provider.invalid",
            "protocol": "openai_chat_completions",
            "model_id": model_id,
            "model_snapshot": "manual-2026-08-26",
        }
    )
    return CreateRunCommand(
        mode=RunMode.OFFICIAL_REPLAY,
        recipe_ids=recipes,
        provider=provider,
        budget=ExternalCallBudget(),
        reviewer_id=_reviewer_id(factory),
    )


def _service(factory: sessionmaker[Session]) -> HumanTestRunService:
    return HumanTestRunService(session_factory=factory, now_factory=lambda: NOW)


def test_create_run_freezes_snapshots_and_is_idempotent(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    command_value = _command(factory)

    created = service.create(command_value, idempotency_key="run-create-1")
    replay = service.create(command_value, idempotency_key="run-create-1")

    assert replay.run_id == created.run_id
    assert created.status == RunStatus.CREATED
    assert tuple(created.recipe_ids) == command_value.recipe_ids
    assert created.provider_config_snapshot == command_value.provider.model_dump(mode="json")
    assert "api_key" not in str(created.provider_config_snapshot).lower()
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(LocalHumanTestItem)
            .where(LocalHumanTestItem.run_id == created.run_id)
        ) == len(command_value.recipe_ids)

    with pytest.raises(RunIdempotencyConflict):
        service.create(
            _command(factory, model_id="deepseek-reasoner"),
            idempotency_key="run-create-1",
        )


def test_two_workers_cannot_claim_the_same_run_item(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    created = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-claim-1",
    )
    barrier = Barrier(2)

    def claim(worker_id: str) -> RunClaim | None:
        barrier.wait()
        return service.claim_next(worker_id, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = [
            future.result() for future in (executor.submit(claim, "a"), executor.submit(claim, "b"))
        ]

    claimed = [value for value in claims if value is not None]
    assert len(claimed) == 1
    assert claimed[0].run_id == created.run_id


def test_expired_lease_is_recovered_but_unknown_outcome_is_not_replayed(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    created = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-recover-1",
    )
    first = service.claim_next("worker-a", now=NOW)
    assert first is not None
    assert service.claim_next("worker-b", now=NOW + timedelta(seconds=59)) is None
    recovered = service.claim_next("worker-b", now=NOW + timedelta(seconds=61))
    assert recovered is not None
    assert recovered.item_id == first.item_id

    service.transition_item(
        recovered.item_id,
        expected=ItemStatus.CREATED,
        target=ItemStatus.ACQUIRING,
        now=NOW + timedelta(seconds=62),
    )
    service.transition_item(
        recovered.item_id,
        expected=ItemStatus.ACQUIRING,
        target=ItemStatus.EXTRACTING,
        now=NOW + timedelta(seconds=63),
    )
    service.transition_item(
        recovered.item_id,
        expected=ItemStatus.EXTRACTING,
        target=ItemStatus.UNKNOWN_OUTCOME,
        error_code="PROVIDER_OUTCOME_UNKNOWN",
        now=NOW + timedelta(seconds=64),
    )
    service.release_lease(created.run_id, "worker-b", now=NOW + timedelta(seconds=64))
    assert service.claim_next("worker-c", now=NOW + timedelta(minutes=5)) is None


def test_budget_reservations_commit_before_effect_and_never_exceed_limits(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    run = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-budget-1",
    )
    assert service.claim_next("budget-worker", now=NOW) is not None

    assert [service.record_official_request(run.run_id, "budget-worker") for _ in range(9)] == list(
        range(1, 10)
    )
    with pytest.raises(BudgetExhausted):
        service.record_official_request(run.run_id, "budget-worker")
    assert [service.record_llm_call(run.run_id, "budget-worker") for _ in range(8)] == list(
        range(1, 9)
    )
    with pytest.raises(BudgetExhausted):
        service.record_llm_call(run.run_id, "budget-worker")

    with factory() as session:
        persisted = session.get(LocalHumanTestRun, run.run_id)
        assert persisted is not None
        assert persisted.official_request_count == 9
        assert persisted.llm_call_count == 8


def test_forbidden_skip_and_cancellation_between_stages(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    run = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-cancel-1",
    )
    with factory() as session:
        item_id = session.scalar(
            select(LocalHumanTestItem.item_id).where(LocalHumanTestItem.run_id == run.run_id)
        )
    assert item_id is not None

    with pytest.raises(ItemTransitionError):
        service.transition_item(
            item_id,
            expected=ItemStatus.CREATED,
            target=ItemStatus.FACT_REVIEW,
        )
    cancelled = service.request_cancel(run.run_id)
    assert cancelled.status == RunStatus.CANCELLED
    with factory() as session:
        assert session.get(LocalHumanTestItem, item_id).status == ItemStatus.CANCELLED  # type: ignore[union-attr]


def test_worker_processes_one_claim_and_releases_lease(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    run = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-worker-1",
    )
    processed: list[UUID] = []

    class Processor:
        def process(self, item_id: UUID) -> None:
            processed.append(item_id)
            service.transition_item(
                item_id,
                expected=ItemStatus.CREATED,
                target=ItemStatus.ACQUIRING,
                now=NOW,
            )

    worker = HumanTestWorker(
        service=service,
        processor=Processor(),
        worker_id="worker-once",
        clock=lambda: NOW,
    )
    assert worker.run_once() is True
    assert len(processed) == 1
    with factory() as session:
        persisted = session.get(LocalHumanTestRun, run.run_id)
        assert persisted is not None
        assert persisted.lease_owner is None
        assert persisted.lease_expires_at is None


def test_interrupted_worker_recovers_only_after_lease_expiry(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-worker-interrupted-1",
    )

    class InterruptedProcessor:
        def process(self, item_id: UUID) -> None:
            raise RuntimeError("synthetic interruption")

    worker = HumanTestWorker(
        service=service,
        processor=InterruptedProcessor(),
        worker_id="interrupted-worker",
        clock=lambda: NOW,
    )
    assert worker.run_once() is True
    assert service.claim_next("replacement", now=NOW + timedelta(seconds=59)) is None
    assert service.claim_next("replacement", now=NOW + timedelta(seconds=61)) is not None


def test_lease_renewal_is_owner_bound_and_extends_from_database_state(
    factory: sessionmaker[Session],
) -> None:
    service = _service(factory)
    run = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-renew-1",
    )
    assert service.claim_next("lease-owner", now=NOW) is not None

    with pytest.raises(LeaseConflict):
        service.renew_lease(run.run_id, "different-worker", now=NOW + timedelta(seconds=10))
    renewed = service.renew_lease(
        run.run_id,
        "lease-owner",
        now=NOW + timedelta(seconds=50),
    )
    assert renewed == NOW + timedelta(seconds=110)
    assert service.claim_next("different-worker", now=NOW + timedelta(seconds=61)) is None


def test_run_completion_requires_terminal_items(factory: sessionmaker[Session]) -> None:
    service = _service(factory)
    run = service.create(
        _command(factory, recipes=("zj-policy",)),
        idempotency_key="run-complete-1",
    )
    with pytest.raises(ItemTransitionError, match="RUN_HAS_NONTERMINAL_ITEMS"):
        service.complete_run(run.run_id)

    service.request_cancel(run.run_id)
    completed = service.complete_run(run.run_id)
    assert completed.status == RunStatus.CANCELLED
