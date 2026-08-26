import json
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.contracts.phase9b import ModelAttemptOutcome
from deepaha.local_human_test.contracts import (
    CreateRunCommand,
    ItemStatus,
    ProviderConfigSnapshot,
    RunMode,
)
from deepaha.local_human_test.extraction import P9BExtractionCoordinator
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.runs import HumanTestRunService
from deepaha.opportunities.models import OpportunityVersion
from deepaha.p9b.gateway import GatewayExecutor
from deepaha.p9b.hashing import canonical_json_bytes, model_invocation_identity
from deepaha.p9b.models import (
    EgressDecision,
    ExtractionCandidate,
    ExtractionCandidateEvidence,
    ExtractionRunInputBlock,
    ModelCall,
    ModelCallAttempt,
    ModelTaskSpec,
    ProviderEgressPolicySnapshot,
    SourceBundleMember,
)
from deepaha.p9b.provider import ProviderAttemptResult, ProviderInvocation
from deepaha.review.models import ReviewerAccountModel
from tests.integration.p9b_gateway_support import GATEWAY_MESSAGES, seed_gateway_authority

pytestmark = pytest.mark.integration
BUCKET = "deepaha-human-test"
WORKER_ID = "human-extraction-worker"


def _temporary_database(database_url: str) -> tuple[str, Engine, URL, str]:
    database_name = f"deepaha_human_extraction_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_human_extraction_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    temporary_url = url.set(database=database_name)
    return (
        database_name,
        maintenance,
        temporary_url,
        temporary_url.render_as_string(hide_password=False),
    )


@pytest.fixture(scope="module")
def human_extraction_engine(database_url: str) -> Iterator[Engine]:
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


class StructuredResponseAdapter:
    supports_idempotency = True

    def __init__(
        self,
        *,
        object_store: LocalFileObjectStore,
        unknown_block: bool = False,
        provider: str = "local-provider",
        fact_field_name: str = "application_deadline",
        fact_value: object = "2026-09-01",
        facts: tuple[tuple[str, object], ...] | None = None,
    ) -> None:
        self.provider = provider
        self._object_store = object_store
        self._unknown_block = unknown_block
        self._fact_field_name = fact_field_name
        self._fact_value = fact_value
        self._facts = facts
        self.invocations: list[ProviderInvocation] = []

    def invoke(self, request: ProviderInvocation) -> ProviderAttemptResult:
        self.invocations.append(request)
        prompt = json.loads(request.messages[1].content)
        block_id = (
            "019d0000-0000-7000-8000-000000009999"
            if self._unknown_block
            else prompt["blocks"][0]["block_id"]
        )
        extracted = {
            "schema_version": "0.8.0",
            "facts": [
                {
                    "field_name": field_name,
                    "raw_value": value,
                    "normalized_value_candidate": value,
                    "evidence_block_ids": [block_id],
                    "confidence": 0.9,
                    "abstained": False,
                    "reason_code": "OFFICIAL_TEXT_EXPLICIT",
                }
                for field_name, value in (
                    self._facts or ((self._fact_field_name, self._fact_value),)
                )
            ],
            "rules": [],
            "uncertainties": [],
        }
        body = json.dumps(
            {
                "id": "synthetic-response-1",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(extracted),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 30},
            }
        ).encode()
        digest = sha256(body).hexdigest()
        metadata = self._object_store.put_bytes_if_absent(
            key=f"provider-responses/{request.model_call_id}/{request.attempt_id}.json",
            content=body,
            media_type="application/json",
            sha256=digest,
        )
        return ProviderAttemptResult(
            outcome=ModelAttemptOutcome.SUCCEEDED,
            provider_http_status=200,
            error_code=None,
            provider_response_id=None,
            raw_response_reference_kind="INTERNAL_OBJECT",
            raw_response_storage_bucket=metadata.bucket,
            raw_response_object_key=metadata.key,
            raw_response_sha256=metadata.sha256,
            response_hash=digest,
            parsed_result_hash=sha256(canonical_json_bytes(extracted)).hexdigest(),
            input_tokens=50,
            output_tokens=30,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_status="COST_NOT_REPORTED",
            monetary_cost=None,
            latency_ms=1,
        )


def _seed_item(
    engine: Engine,
    *,
    policy_confirmed: bool = True,
) -> tuple[sessionmaker[Session], HumanTestRunService, UUID]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    reviewer_id = uuid7()
    with factory.begin() as session:
        authority = seed_gateway_authority(session)
        member = session.scalar(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == authority.source_bundle_revision_id
            )
        )
        assert member is not None
        session.add(
            ReviewerAccountModel(
                reviewer_id=reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"human-extractor-{reviewer_id}",
                roles=["LOCAL_TEST_OPERATOR"],
                allowed_purposes=["OPPORTUNITY_FACT_VALIDATION"],
                created_at=datetime.now(UTC),
            )
        )
        recipe_id = member.recipe_id
        source_id = member.source_id
        endpoint_id = member.endpoint_id
        evaluation_id = member.acquisition_evaluation_id
        document_id = member.document_id
        opportunity_id = authority.intent.opportunity_id
        revision_id = authority.source_bundle_revision_id
        opportunity_version = session.get(
            OpportunityVersion,
            (opportunity_id, authority.intent.opportunity_version),
        )
        assert opportunity_version is not None
        opportunity_version.review_status = "PENDING"

    provider = ProviderConfigSnapshot.model_validate(
        {
            "provider": "local-provider",
            "base_url": "https://provider.invalid",
            "protocol": "openai_chat_completions",
            "model_id": "local-model",
            "model_snapshot": "local-model-2026-08-26",
            "provider_region": "local-test" if policy_confirmed else "unknown",
            "zero_retention": False,
            "training_use": True,
            "supports_idempotency": True,
        }
    )
    service = HumanTestRunService(
        session_factory=factory,
        now_factory=lambda: datetime.now(UTC),
    )
    run = service.create(
        CreateRunCommand(
            mode=RunMode.OFFICIAL_REPLAY,
            recipe_ids=(str(recipe_id),),
            provider=provider,
            reviewer_id=reviewer_id,
        ),
        idempotency_key=f"extract-{uuid7()}",
    )
    claim = service.claim_next(WORKER_ID)
    assert claim is not None
    service.transition_item(
        claim.item_id,
        expected=ItemStatus.CREATED,
        target=ItemStatus.ACQUIRING,
    )
    service.transition_item(
        claim.item_id,
        expected=ItemStatus.ACQUIRING,
        target=ItemStatus.EXTRACTING,
        references={
            "source_id": source_id,
            "endpoint_id": endpoint_id,
            "acquisition_evaluation_id": evaluation_id,
            "document_id": document_id,
            "opportunity_id": opportunity_id,
            "source_bundle_revision_id": revision_id,
        },
    )
    with factory() as session:
        persisted = session.get(LocalHumanTestRun, run.run_id)
        assert persisted is not None
        assert persisted.llm_call_count == 0
    return factory, service, claim.item_id


def _coordinator(
    engine: Engine,
    tmp_path: Path,
    *,
    unknown_block: bool = False,
    policy_confirmed: bool = True,
    fact_field_name: str = "application_deadline",
    fact_value: object = "2026-09-01",
    facts: tuple[tuple[str, object], ...] | None = None,
) -> tuple[P9BExtractionCoordinator, StructuredResponseAdapter, sessionmaker[Session], UUID]:
    factory, service, item_id = _seed_item(engine, policy_confirmed=policy_confirmed)
    store = LocalFileObjectStore(root=tmp_path, bucket=BUCKET)
    adapter = StructuredResponseAdapter(
        object_store=store,
        unknown_block=unknown_block,
        fact_field_name=fact_field_name,
        fact_value=fact_value,
        facts=facts,
    )
    gateway = GatewayExecutor(session_factory=factory, adapter=adapter, sleeper=lambda _: None)
    return (
        P9BExtractionCoordinator(
            session_factory=factory,
            gateway=gateway,
            object_store=store,
            response_bucket=BUCKET,
            run_service=service,
            worker_id=WORKER_ID,
        ),
        adapter,
        factory,
        item_id,
    )


def test_gateway_registration_creates_no_attempt_or_adapter_dispatch(
    human_extraction_engine: Engine,
    tmp_path: Path,
) -> None:
    factory = sessionmaker(bind=human_extraction_engine, expire_on_commit=False)
    with factory.begin() as session:
        authority = seed_gateway_authority(session)
    store = LocalFileObjectStore(root=tmp_path, bucket=BUCKET)
    adapter = StructuredResponseAdapter(
        object_store=store,
        provider=authority.intent.provider,
    )
    gateway = GatewayExecutor(session_factory=factory, adapter=adapter)

    registered = gateway.register(intent=authority.intent, messages=GATEWAY_MESSAGES)

    assert registered.model_call_id == authority.intent.model_call_id
    assert adapter.invocations == []
    with factory() as session:
        assert session.get(ModelCall, registered.model_call_id) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ModelCallAttempt)
                .where(ModelCallAttempt.model_call_id == registered.model_call_id)
            )
            == 0
        )


def test_gateway_response_persists_exact_input_evidence_and_shared_identity(
    human_extraction_engine: Engine,
    tmp_path: Path,
) -> None:
    coordinator, adapter, factory, item_id = _coordinator(human_extraction_engine, tmp_path)

    outcome = coordinator.extract(item_id)

    assert outcome.status is ItemStatus.FACT_REVIEW
    assert len(outcome.candidate_ids) == 1
    assert len(adapter.invocations) == 1
    with factory() as session:
        item = session.get(LocalHumanTestItem, item_id)
        call = session.get(ModelCall, outcome.model_call_id)
        decision = session.get(EgressDecision, call.egress_decision_id if call else None)
        assert item is not None and call is not None and decision is not None
        task = session.scalar(
            select(ModelTaskSpec).where(ModelTaskSpec.task_name == call.task_spec_name)
        )
        policy = session.get(
            ProviderEgressPolicySnapshot,
            decision.provider_policy_snapshot_id,
        )
        assert task is not None and policy is not None
        assert task.provider_capabilities == ["PROVIDER_TRANSIENT_RETENTION"]
        assert policy.zero_retention is False
        assert policy.training_use is True
        assert policy.retention_class == "PROVIDER_TRANSIENT_RETENTION"
        assert call.retention_class == "PROVIDER_TRANSIENT_RETENTION"
        run = session.get(LocalHumanTestRun, item.run_id)
        assert run is not None and run.llm_call_count == 1
        assert item.extraction_run_id == outcome.extraction_run_id
        assert call.canonical_request_hash == decision.actual_payload_hash
        assert (
            call.canonical_request_hash
            == model_invocation_identity(adapter.invocations[0]).canonical_request_hash
        )
        run_blocks = set(
            session.scalars(
                select(ExtractionRunInputBlock.block_id).where(
                    ExtractionRunInputBlock.extraction_run_id == outcome.extraction_run_id
                )
            )
        )
        evidence_blocks = set(
            session.scalars(
                select(ExtractionCandidateEvidence.block_id).where(
                    ExtractionCandidateEvidence.candidate_id.in_(outcome.candidate_ids)
                )
            )
        )
        assert evidence_blocks and evidence_blocks <= run_blocks
        assert (
            session.scalar(
                select(func.count())
                .select_from(ModelCallAttempt)
                .where(ModelCallAttempt.model_call_id == outcome.model_call_id)
            )
            == 1
        )


def test_unknown_response_block_creates_no_candidate(
    human_extraction_engine: Engine,
    tmp_path: Path,
) -> None:
    coordinator, adapter, factory, item_id = _coordinator(
        human_extraction_engine,
        tmp_path,
        unknown_block=True,
    )

    outcome = coordinator.extract(item_id)

    assert outcome.status is ItemStatus.EVIDENCE_BINDING_INVALID
    assert len(adapter.invocations) == 1
    with factory() as session:
        item = session.get(LocalHumanTestItem, item_id)
        assert item is not None
        assert item.extraction_run_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExtractionCandidate)
                .where(ExtractionCandidate.opportunity_id == item.opportunity_id)
            )
            == 0
        )


def test_unconfirmed_provider_policy_fails_before_model_call_and_adapter(
    human_extraction_engine: Engine,
    tmp_path: Path,
) -> None:
    coordinator, adapter, factory, item_id = _coordinator(
        human_extraction_engine,
        tmp_path,
        policy_confirmed=False,
    )

    outcome = coordinator.extract(item_id)

    assert outcome.status is ItemStatus.FAILED_CONFIG
    assert adapter.invocations == []
    with factory() as session:
        item = session.get(LocalHumanTestItem, item_id)
        assert item is not None
        run = session.get(LocalHumanTestRun, item.run_id)
        assert run is not None and run.llm_call_count == 0
