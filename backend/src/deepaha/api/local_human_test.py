from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.api.personal import PRIVATE_CACHE_CONTROL
from deepaha.artifacts.models import RawArtifact
from deepaha.core.settings import Settings, get_settings
from deepaha.db.session import get_engine, get_write_session
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef
from deepaha.local_human_test.bootstrap import (
    ActiveRecipeView,
    BootstrapReviewRequired,
    ProvisionalOpportunityService,
    build_active_recipe_views,
)
from deepaha.local_human_test.contracts import (
    CreateRunCommand,
    ExternalCallBudget,
    ItemStatus,
    ProviderConfigSnapshot,
    RunMode,
)
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.provider_config import (
    LocalProviderConfigStore,
    ProviderConfigError,
    ProviderConfigIdempotencyConflict,
    ProviderConfigStatus,
    SaveProviderConfig,
    WindowsDirectoryHardener,
    WindowsDpapiProtector,
)
from deepaha.local_human_test.publication import (
    LocalCatalogPublicationService,
    LocalPublicationError,
    PublicationIdempotencyConflict,
)
from deepaha.local_human_test.review import (
    FactDecisionCommand,
    HumanFactReviewService,
    HumanReviewError,
    HumanRuleReviewService,
    ReviewIdempotencyConflict,
    RuleDecisionCommand,
    require_human_fact_reviewer,
)
from deepaha.local_human_test.runs import (
    HumanTestRunService,
    ItemTransitionError,
    RunIdempotencyConflict,
)
from deepaha.p9b.models import (
    EgressDecision,
    ExtractionCandidate,
    ExtractionCandidateEvidence,
    FactVerificationDecisionModel,
    ModelCall,
    ModelCallAttempt,
    ModelCallFinalization,
    RuleApprovalDecisionModel,
    RuleCandidateModel,
)
from deepaha.review.auth import (
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
    resolve_reviewer_principal,
)
from deepaha.sources.models import Source
from deepaha.sources.registry import load_registry_manifest

router = APIRouter(prefix="/api/v1/local-human-test", tags=["local-human-test"])
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class LocalApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class SourceRecipeResponse(LocalApiModel):
    recipe_id: UUID
    source_id: UUID
    endpoint_id: UUID
    authority_name: str
    jurisdiction: str | None
    usage_role: str
    official_url: str
    official_host: str
    verified_at: datetime
    maximum_requests: int
    opportunity_type_hint: str


class CreateRunRequest(LocalApiModel):
    mode: RunMode
    recipe_ids: tuple[str, ...]
    budget: ExternalCallBudget = Field(default_factory=ExternalCallBudget)
    confirm_live_official: bool = False


class RunResponse(LocalApiModel):
    run_id: UUID
    mode: str
    recipe_ids: tuple[str, ...]
    provider: str
    model_id: str
    model_snapshot: str
    budget: dict[str, object]
    status: str
    official_request_count: int
    llm_call_count: int
    terminal_reason_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ItemResponse(LocalApiModel):
    item_id: UUID
    run_id: UUID
    recipe_id: str
    status: str
    error_code: str | None
    source_id: UUID | None
    endpoint_id: UUID | None
    document_id: UUID | None
    opportunity_id: UUID | None
    model_call_id: UUID | None
    verified_fact_set_id: UUID | None
    created_at: datetime
    updated_at: datetime


class RunDetailResponse(LocalApiModel):
    run: RunResponse
    items: tuple[ItemResponse, ...]


class AttemptAuditResponse(LocalApiModel):
    attempt_number: int
    outcome: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    cost_status: str | None
    monetary_cost: object | None


class ModelAuditResponse(LocalApiModel):
    model_call_id: UUID
    canonical_request_hash: str
    canonical_message_hashes: tuple[str, ...]
    actual_payload_hash: str | None
    egress_decision: str
    final_status: str | None
    terminal_disposition: str | None
    attempts: tuple[AttemptAuditResponse, ...]


class EvidenceBlockResponse(LocalApiModel):
    evidence_ref_id: UUID
    block_id: UUID
    document_id: UUID
    block_type: str
    canonical_text_or_value: str
    structural_locator: dict[str, object]
    source_tier: str
    source_url: str


class FactCandidateResponse(LocalApiModel):
    candidate_id: UUID
    field_name: str
    raw_value: object | None
    normalized_value_candidate: object | None
    confidence: float | None
    abstained: bool
    candidate_reason_code: str
    decision: str | None
    evidence: tuple[EvidenceBlockResponse, ...]


class RuleCandidateResponse(LocalApiModel):
    rule_candidate_id: UUID
    proposed_rule_payload: dict[str, object]
    decision: str | None


class PublicationPreviewResponse(LocalApiModel):
    item_id: UUID
    opportunity_id: UUID
    base_version: int
    approved_field_names: tuple[str, ...]
    missing_field_names: tuple[str, ...]
    content_use_basis: str | None
    official_evidence_complete: bool
    eligibility_ceiling: str
    blocker_codes: tuple[str, ...]
    eligible: bool


class ItemDetailResponse(LocalApiModel):
    item: ItemResponse
    model_audit: ModelAuditResponse | None
    candidates: tuple[FactCandidateResponse, ...]
    rules: tuple[RuleCandidateResponse, ...]
    publication_preview: PublicationPreviewResponse | None = None


class FactDecisionRequest(LocalApiModel):
    candidate_id: UUID
    decision: Literal["APPROVE", "REJECT", "UNKNOWN"]
    reason: str = Field(min_length=1, max_length=500)


class FactDecisionResponse(LocalApiModel):
    decision: dict[str, object]
    promotion: dict[str, object] | None
    rules: dict[str, object] | None


class RuleDecisionRequest(LocalApiModel):
    rule_candidate_id: UUID
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    reason: str = Field(min_length=1, max_length=500)


class RuleDecisionResponse(LocalApiModel):
    decision_id: UUID
    rule_candidate_id: UUID
    decision: str
    eligibility_ceiling: str


class PublicationResultResponse(LocalApiModel):
    decision_id: UUID
    item_id: UUID
    opportunity_id: UUID
    opportunity_version: int
    content_sha256: str
    repeated: bool


class LocalRunQuery:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_runs(self) -> tuple[LocalHumanTestRun, ...]:
        return tuple(
            self._session.scalars(
                select(LocalHumanTestRun)
                .order_by(LocalHumanTestRun.created_at.desc(), LocalHumanTestRun.run_id)
                .limit(50)
            )
        )

    def get_run(
        self,
        run_id: UUID,
    ) -> tuple[LocalHumanTestRun, tuple[LocalHumanTestItem, ...]] | None:
        run = self._session.get(LocalHumanTestRun, run_id)
        if run is None:
            return None
        items = tuple(
            self._session.scalars(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.run_id == run_id)
                .order_by(LocalHumanTestItem.created_at, LocalHumanTestItem.item_id)
            )
        )
        return run, items


class LocalItemQuery:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_items(
        self,
        run_id: UUID | None = None,
    ) -> tuple[LocalHumanTestItem, ...]:
        statement = select(LocalHumanTestItem)
        if run_id is not None:
            statement = statement.where(LocalHumanTestItem.run_id == run_id)
        return tuple(
            self._session.scalars(
                statement.order_by(
                    LocalHumanTestItem.created_at.desc(),
                    LocalHumanTestItem.item_id,
                ).limit(100)
            )
        )

    def get_item(self, item_id: UUID) -> LocalHumanTestItem | None:
        return self._session.get(LocalHumanTestItem, item_id)

    def get_item_detail(self, item_id: UUID) -> dict[str, object] | None:
        item = self._session.get(LocalHumanTestItem, item_id)
        if item is None:
            return None
        return {
            "item": item,
            "model_audit": self._model_audit(item.model_call_id),
            "candidates": self._candidates(item),
            "rules": self._rules(item),
        }

    def _model_audit(self, model_call_id: UUID | None) -> dict[str, object] | None:
        if model_call_id is None:
            return None
        call = self._session.get(ModelCall, model_call_id)
        if call is None:
            return None
        egress = self._session.get(EgressDecision, call.egress_decision_id)
        if egress is None:
            return None
        finalization = self._session.get(ModelCallFinalization, model_call_id)
        attempts = tuple(
            self._session.scalars(
                select(ModelCallAttempt)
                .where(ModelCallAttempt.model_call_id == model_call_id)
                .order_by(ModelCallAttempt.attempt_number)
            )
        )
        return {
            "model_call_id": call.model_call_id,
            "canonical_request_hash": call.canonical_request_hash,
            "canonical_message_hashes": tuple(call.canonical_message_hashes),
            "actual_payload_hash": egress.actual_payload_hash,
            "egress_decision": egress.decision,
            "final_status": None if finalization is None else finalization.status,
            "terminal_disposition": (None if finalization is None else finalization.disposition),
            "attempts": tuple(
                {
                    "attempt_number": attempt.attempt_number,
                    "outcome": attempt.outcome,
                    "input_tokens": attempt.input_tokens,
                    "output_tokens": attempt.output_tokens,
                    "latency_ms": attempt.latency_ms,
                    "cost_status": attempt.cost_status,
                    "monetary_cost": attempt.monetary_cost,
                }
                for attempt in attempts
            ),
        }

    def _candidates(self, item: LocalHumanTestItem) -> tuple[dict[str, object], ...]:
        if item.extraction_run_id is None:
            return ()
        candidates = tuple(
            self._session.scalars(
                select(ExtractionCandidate)
                .where(ExtractionCandidate.extraction_run_id == item.extraction_run_id)
                .order_by(ExtractionCandidate.field_name, ExtractionCandidate.candidate_id)
            )
        )
        values: list[dict[str, object]] = []
        for candidate in candidates:
            decision = self._session.scalar(
                select(FactVerificationDecisionModel).where(
                    FactVerificationDecisionModel.candidate_id == candidate.candidate_id
                )
            )
            evidence_rows = self._session.execute(
                select(DocumentBlock, EvidenceRef, Document, RawArtifact, Source)
                .select_from(ExtractionCandidateEvidence)
                .join(
                    DocumentBlock,
                    DocumentBlock.block_id == ExtractionCandidateEvidence.block_id,
                )
                .join(
                    EvidenceRef,
                    EvidenceRef.evidence_ref_id == ExtractionCandidateEvidence.evidence_ref_id,
                )
                .join(Document, Document.document_id == EvidenceRef.document_id)
                .join(RawArtifact, RawArtifact.artifact_id == Document.artifact_id)
                .join(Source, Source.source_id == RawArtifact.source_id)
                .where(
                    ExtractionCandidateEvidence.candidate_id == candidate.candidate_id,
                    Source.tier.in_(("OFFICIAL_PRIMARY", "OFFICIAL_AGGREGATOR")),
                    Source.source_id == item.source_id,
                )
                .order_by(DocumentBlock.ordinal, DocumentBlock.block_id)
            ).all()
            values.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "field_name": candidate.field_name,
                    "raw_value": candidate.raw_value,
                    "normalized_value_candidate": (candidate.normalized_value_candidate),
                    "confidence": candidate.confidence,
                    "abstained": candidate.abstained,
                    "candidate_reason_code": candidate.candidate_reason_code,
                    "decision": None if decision is None else decision.decision,
                    "evidence": tuple(
                        {
                            "evidence_ref_id": evidence_ref.evidence_ref_id,
                            "block_id": block.block_id,
                            "document_id": document.document_id,
                            "block_type": block.block_type,
                            "canonical_text_or_value": block.canonical_text_or_value,
                            "structural_locator": block.structural_locator,
                            "source_tier": source.tier,
                            "source_url": artifact.resolved_url,
                        }
                        for block, evidence_ref, document, artifact, source in evidence_rows
                    ),
                }
            )
        return tuple(values)

    def _rules(self, item: LocalHumanTestItem) -> tuple[dict[str, object], ...]:
        if item.verified_fact_set_id is None:
            return ()
        candidates = tuple(
            self._session.scalars(
                select(RuleCandidateModel)
                .where(RuleCandidateModel.verified_fact_set_id == item.verified_fact_set_id)
                .order_by(RuleCandidateModel.rule_candidate_id)
            )
        )
        return tuple(
            {
                "rule_candidate_id": candidate.rule_candidate_id,
                "proposed_rule_payload": candidate.proposed_rule_payload,
                "decision": (
                    None
                    if (
                        decision := self._session.scalar(
                            select(RuleApprovalDecisionModel).where(
                                RuleApprovalDecisionModel.rule_candidate_id
                                == candidate.rule_candidate_id
                            )
                        )
                    )
                    is None
                    else decision.decision
                ),
            }
            for candidate in candidates
        )


def _problem(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def require_local_human_test(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    host = (request.url.hostname or "").lower().rstrip(".")
    if (
        settings.environment != "development"
        or not settings.local_human_test_enabled
        or settings.local_human_test_root is None
        or settings.local_human_test_bind_host not in LOOPBACK_HOSTS
        or host not in LOOPBACK_HOSTS
    ):
        raise _problem(404, "LOCAL_HUMAN_TEST_NOT_FOUND")


def require_local_test_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewerPrincipal:
    values = request.headers.getlist("authorization")
    try:
        if len(values) != 1:
            raise ReviewerAuthenticationError("reviewer authentication failed")
        engine = get_engine(settings)
        try:
            with Session(engine) as session:
                return resolve_reviewer_principal(values[0], session, settings)
        finally:
            engine.dispose()
    except ReviewerAuthenticationError as error:
        raise _problem(401, "LOCAL_REVIEWER_AUTHENTICATION_FAILED") from error


def require_local_idempotency_key(request: Request) -> str:
    values = request.headers.getlist("idempotency-key")
    if len(values) != 1:
        raise _problem(400, "IDEMPOTENCY_KEY_REQUIRED")
    value = values[0]
    if (
        not 1 <= len(value) <= 128
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise _problem(400, "IDEMPOTENCY_KEY_INVALID")
    return value


def get_local_provider_config_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LocalProviderConfigStore:
    root = settings.local_human_test_root
    if root is None:
        raise _problem(404, "LOCAL_HUMAN_TEST_NOT_FOUND")
    return LocalProviderConfigStore(
        root=Path(root),
        protector=WindowsDpapiProtector(),
        hardener=WindowsDirectoryHardener(),
    )


def get_local_recipe_views() -> tuple[ActiveRecipeView, ...]:
    project_root = Path(__file__).resolve().parents[4]
    recipes = load_recipe_manifest(project_root / "config" / "acquisition" / "recipes.v1.json")
    registry = load_registry_manifest(
        project_root / "config" / "sources" / "phase2-official-endpoints.json"
    )
    return build_active_recipe_views(recipes.recipes, registry)


def _factory(session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def get_local_run_service(
    session: Annotated[Session, Depends(get_write_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HumanTestRunService:
    return HumanTestRunService(
        session_factory=_factory(session),
        lease_seconds=settings.local_human_test_lease_seconds,
    )


def get_local_run_query(
    session: Annotated[Session, Depends(get_write_session)],
) -> LocalRunQuery:
    return LocalRunQuery(session)


def get_local_item_query(
    session: Annotated[Session, Depends(get_write_session)],
) -> LocalItemQuery:
    return LocalItemQuery(session)


def get_local_fact_review_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> HumanFactReviewService:
    return HumanFactReviewService(session_factory=_factory(session))


def get_local_rule_review_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> HumanRuleReviewService:
    return HumanRuleReviewService(session_factory=_factory(session))


def get_local_publication_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> LocalCatalogPublicationService:
    return LocalCatalogPublicationService(session_factory=_factory(session))


def get_local_provisional_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> ProvisionalOpportunityService:
    project_root = Path(__file__).resolve().parents[4]
    recipes = load_recipe_manifest(project_root / "config" / "acquisition" / "recipes.v1.json")
    return ProvisionalOpportunityService(
        session_factory=_factory(session),
        recipes=recipes.recipes,
        clock=lambda: datetime.now(UTC),
    )


def _authorize_operator(principal: ReviewerPrincipal) -> None:
    try:
        require_reviewer_authority(
            principal,
            ReviewerRole.LOCAL_TEST_OPERATOR,
            "OPPORTUNITY_FACT_VALIDATION",
        )
    except ReviewerAuthenticationError as error:
        raise _problem(403, "LOCAL_TEST_OPERATOR_REQUIRED") from error


def _authorize_validation_reviewer(principal: ReviewerPrincipal) -> None:
    try:
        require_human_fact_reviewer(principal)
    except HumanReviewError as error:
        raise _problem(403, "LOCAL_VALIDATION_REVIEWER_REQUIRED") from error


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL


@router.get("/config/provider")
def provider_status(
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    store: Annotated[LocalProviderConfigStore, Depends(get_local_provider_config_store)],
) -> ProviderConfigStatus:
    _authorize_operator(principal)
    try:
        result = store.status()
    except ProviderConfigError as error:
        raise _problem(503, "PROVIDER_CONFIG_UNAVAILABLE") from error
    _private(response)
    return result


@router.put("/config/provider")
def save_provider(
    command: SaveProviderConfig,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    store: Annotated[LocalProviderConfigStore, Depends(get_local_provider_config_store)],
) -> ProviderConfigStatus:
    _authorize_operator(principal)
    try:
        result = store.save(command, idempotency_key=idempotency_key)
    except ProviderConfigIdempotencyConflict as error:
        raise _problem(409, "PROVIDER_CONFIG_IDEMPOTENCY_CONFLICT") from error
    except ProviderConfigError as error:
        raise _problem(503, "PROVIDER_CONFIG_UNAVAILABLE") from error
    _private(response)
    return result


@router.delete("/config/provider/secret")
def delete_provider_secret(
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    _idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    store: Annotated[LocalProviderConfigStore, Depends(get_local_provider_config_store)],
) -> ProviderConfigStatus:
    _authorize_operator(principal)
    try:
        result = store.delete_secret()
    except ProviderConfigError as error:
        raise _problem(503, "PROVIDER_CONFIG_UNAVAILABLE") from error
    _private(response)
    return result


def _run_response(run: object) -> RunResponse:
    snapshot = getattr(run, "provider_config_snapshot")
    if not isinstance(snapshot, dict):
        raise _problem(503, "LOCAL_RUN_SNAPSHOT_INVALID")
    return RunResponse.model_validate(
        {
            "run_id": getattr(run, "run_id"),
            "mode": getattr(run, "mode"),
            "recipe_ids": getattr(run, "recipe_ids"),
            "provider": snapshot.get("provider"),
            "model_id": snapshot.get("model_id"),
            "model_snapshot": snapshot.get("model_snapshot"),
            "budget": getattr(run, "budget"),
            "status": getattr(run, "status"),
            "official_request_count": getattr(run, "official_request_count"),
            "llm_call_count": getattr(run, "llm_call_count"),
            "terminal_reason_code": getattr(run, "terminal_reason_code"),
            "created_at": getattr(run, "created_at"),
            "updated_at": getattr(run, "updated_at"),
            "completed_at": getattr(run, "completed_at"),
        }
    )


@router.get("/sources")
def list_sources(
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    recipes: Annotated[tuple[ActiveRecipeView, ...], Depends(get_local_recipe_views)],
) -> tuple[SourceRecipeResponse, ...]:
    _authorize_operator(principal)
    _private(response)
    return tuple(SourceRecipeResponse.model_validate(value) for value in recipes)


@router.get("/runs")
def list_runs(
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    query: Annotated[LocalRunQuery, Depends(get_local_run_query)],
) -> tuple[RunResponse, ...]:
    _authorize_operator(principal)
    _private(response)
    return tuple(_run_response(run) for run in query.list_runs())


@router.post("/runs", status_code=201)
def create_run(
    command: CreateRunRequest,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    store: Annotated[LocalProviderConfigStore, Depends(get_local_provider_config_store)],
    recipes: Annotated[tuple[ActiveRecipeView, ...], Depends(get_local_recipe_views)],
    service: Annotated[HumanTestRunService, Depends(get_local_run_service)],
) -> RunResponse:
    _authorize_operator(principal)
    if command.mode is RunMode.LIVE_OFFICIAL and not command.confirm_live_official:
        raise _problem(400, "LIVE_OFFICIAL_CONFIRMATION_REQUIRED")
    allowed_recipe_ids = {str(recipe.recipe_id) for recipe in recipes}
    if not command.recipe_ids or not set(command.recipe_ids).issubset(allowed_recipe_ids):
        raise _problem(400, "ACTIVE_RECIPE_SELECTION_INVALID")
    try:
        status = store.status()
    except ProviderConfigError as error:
        raise _problem(503, "PROVIDER_CONFIG_UNAVAILABLE") from error
    if (
        not status.configured
        or not status.egress_ready
        or status.provider is None
        or status.base_url is None
        or status.protocol is None
        or status.model_id is None
        or status.model_snapshot is None
        or status.provider_region is None
        or status.zero_retention is None
        or status.training_use is None
        or status.supports_idempotency is None
    ):
        raise _problem(409, "PROVIDER_NOT_CONFIGURED")
    provider = ProviderConfigSnapshot.model_validate(
        {
            "provider": status.provider,
            "base_url": status.base_url,
            "protocol": status.protocol,
            "model_id": status.model_id,
            "model_snapshot": status.model_snapshot,
            "provider_region": status.provider_region,
            "zero_retention": status.zero_retention,
            "training_use": status.training_use,
            "supports_idempotency": status.supports_idempotency,
        }
    )
    try:
        run = service.create(
            CreateRunCommand(
                mode=command.mode,
                recipe_ids=command.recipe_ids,
                provider=provider,
                budget=command.budget,
                reviewer_id=principal.reviewer_id,
            ),
            idempotency_key=idempotency_key,
        )
    except RunIdempotencyConflict as error:
        raise _problem(409, "RUN_CREATE_IDEMPOTENCY_CONFLICT") from error
    _private(response)
    return _run_response(run)


@router.get("/runs/{run_id}")
def get_run(
    run_id: UUID,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    query: Annotated[LocalRunQuery, Depends(get_local_run_query)],
) -> RunDetailResponse:
    _authorize_operator(principal)
    result = query.get_run(run_id)
    if result is None:
        raise _problem(404, "LOCAL_RUN_NOT_FOUND")
    run, items = result
    _private(response)
    return RunDetailResponse(
        run=_run_response(run),
        items=tuple(ItemResponse.model_validate(item) for item in items),
    )


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: UUID,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    _idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    service: Annotated[HumanTestRunService, Depends(get_local_run_service)],
) -> RunResponse:
    _authorize_operator(principal)
    try:
        run = service.request_cancel(run_id)
    except ItemTransitionError as error:
        raise _problem(409, "LOCAL_RUN_CANCELLATION_CONFLICT") from error
    _private(response)
    return _run_response(run)


@router.get("/items")
def list_items(
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    query: Annotated[LocalItemQuery, Depends(get_local_item_query)],
    run_id: UUID | None = None,
) -> tuple[ItemResponse, ...]:
    _authorize_operator(principal)
    _private(response)
    return tuple(ItemResponse.model_validate(item) for item in query.list_items(run_id))


@router.get("/items/{item_id}")
def get_item(
    item_id: UUID,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    query: Annotated[LocalItemQuery, Depends(get_local_item_query)],
    publication: Annotated[
        LocalCatalogPublicationService,
        Depends(get_local_publication_service),
    ],
) -> ItemDetailResponse:
    _authorize_operator(principal)
    result = query.get_item_detail(item_id)
    if result is None:
        raise _problem(404, "LOCAL_ITEM_NOT_FOUND")
    try:
        preview = publication.preview(item_id)
    except LocalPublicationError:
        preview = None
    result["publication_preview"] = preview
    _private(response)
    return ItemDetailResponse.model_validate(result)


@router.post("/items/{item_id}/bootstrap")
def bootstrap_item(
    item_id: UUID,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    _idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    query: Annotated[LocalItemQuery, Depends(get_local_item_query)],
    provisional: Annotated[
        ProvisionalOpportunityService,
        Depends(get_local_provisional_service),
    ],
    run_service: Annotated[HumanTestRunService, Depends(get_local_run_service)],
) -> ItemResponse:
    _authorize_operator(principal)
    item = query.get_item(item_id)
    if item is None:
        raise _problem(404, "LOCAL_ITEM_NOT_FOUND")
    if ItemStatus(item.status) is ItemStatus.EXTRACTING and item.opportunity_id is not None:
        _private(response)
        return ItemResponse.model_validate(item)
    if ItemStatus(item.status) is not ItemStatus.BOOTSTRAP_REVIEW or item.document_id is None:
        raise _problem(409, "BOOTSTRAP_REVIEW_TARGET_INVALID")
    result = provisional.create(
        document_id=item.document_id,
        recipe_id=UUID(item.recipe_id),
    )
    if isinstance(result, BootstrapReviewRequired):
        code = result.reason_codes[0] if result.reason_codes else "BOOTSTRAP_REVIEW_REQUIRED"
        raise _problem(409, code)
    try:
        transitioned = run_service.transition_item(
            item_id,
            expected=ItemStatus.BOOTSTRAP_REVIEW,
            target=ItemStatus.EXTRACTING,
            references={"opportunity_id": result.opportunity.opportunity_id},
        )
    except ItemTransitionError as error:
        raise _problem(409, "BOOTSTRAP_REVIEW_STATE_CONFLICT") from error
    _private(response)
    return ItemResponse.model_validate(transitioned)


@router.post("/items/{item_id}/facts/decision")
def decide_fact(
    item_id: UUID,
    command: FactDecisionRequest,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    fact_service: Annotated[
        HumanFactReviewService,
        Depends(get_local_fact_review_service),
    ],
    rule_service: Annotated[
        HumanRuleReviewService,
        Depends(get_local_rule_review_service),
    ],
) -> FactDecisionResponse:
    _authorize_validation_reviewer(principal)
    try:
        decision = fact_service.decide(
            FactDecisionCommand(
                item_id=item_id,
                candidate_id=command.candidate_id,
                decision=command.decision,
                reason=command.reason,
            ),
            principal,
            idempotency_key,
        )
        try:
            promotion = fact_service.promote(item_id, principal)
        except HumanReviewError as error:
            if str(error) != "ALL_FACT_CANDIDATES_REQUIRE_DECISION":
                raise
            promotion = None
        rules = None if promotion is None else rule_service.propose_from_verified_facts(item_id)
    except ReviewIdempotencyConflict as error:
        raise _problem(409, str(error)) from error
    except HumanReviewError as error:
        raise _problem(409, str(error)) from error
    _private(response)
    return FactDecisionResponse.model_validate(
        {
            "decision": {
                "decision_id": decision.decision_id,
                "candidate_id": decision.candidate_id,
                "decision": decision.decision,
            },
            "promotion": (
                None
                if promotion is None
                else {
                    "item_id": promotion.item_id,
                    "verified_fact_set_id": promotion.verified_fact_set_id,
                    "promoted_field_names": promotion.promoted_field_names,
                    "retained_unpromoted_decision_count": (
                        promotion.retained_unpromoted_decision_count
                    ),
                }
            ),
            "rules": (
                None
                if rules is None
                else {
                    "item_id": rules.item_id,
                    "candidates": tuple(
                        {
                            "rule_candidate_id": candidate.rule_candidate_id,
                            "field_name": candidate.field_name,
                            "proposed_rule_payload": candidate.proposed_rule_payload,
                            "verified_fact_ids": candidate.verified_fact_ids,
                            "evidence_ref_ids": candidate.evidence_ref_ids,
                        }
                        for candidate in rules.candidates
                    ),
                    "eligibility_ceiling": rules.eligibility_ceiling,
                }
            ),
        }
    )


@router.post("/items/{item_id}/rules/decision")
def decide_rule(
    item_id: UUID,
    command: RuleDecisionRequest,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    service: Annotated[
        HumanRuleReviewService,
        Depends(get_local_rule_review_service),
    ],
) -> RuleDecisionResponse:
    _authorize_validation_reviewer(principal)
    try:
        result = service.decide(
            RuleDecisionCommand(
                item_id=item_id,
                rule_candidate_id=command.rule_candidate_id,
                decision=command.decision,
                reason=command.reason,
            ),
            principal,
            idempotency_key,
        )
    except ReviewIdempotencyConflict as error:
        raise _problem(409, str(error)) from error
    except HumanReviewError as error:
        raise _problem(409, str(error)) from error
    _private(response)
    return RuleDecisionResponse.model_validate(result)


@router.post("/items/{item_id}/publish")
def publish_item(
    item_id: UUID,
    response: Response,
    _guard: Annotated[None, Depends(require_local_human_test)],
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
    idempotency_key: Annotated[str, Depends(require_local_idempotency_key)],
    service: Annotated[
        LocalCatalogPublicationService,
        Depends(get_local_publication_service),
    ],
) -> PublicationResultResponse:
    _authorize_validation_reviewer(principal)
    try:
        result = service.publish(item_id, principal, idempotency_key)
    except PublicationIdempotencyConflict as error:
        raise _problem(409, str(error)) from error
    except LocalPublicationError as error:
        raise _problem(409, str(error)) from error
    _private(response)
    return PublicationResultResponse.model_validate(result)


__all__ = [
    "get_local_fact_review_service",
    "get_local_item_query",
    "get_local_publication_service",
    "get_local_provider_config_store",
    "get_local_provisional_service",
    "get_local_recipe_views",
    "get_local_rule_review_service",
    "get_local_run_query",
    "get_local_run_service",
    "require_local_human_test",
    "require_local_idempotency_key",
    "require_local_test_principal",
    "router",
]
