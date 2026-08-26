from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    SourceRecipe,
    SourceUsageRole,
    ValidationStatus,
)
from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.acquisition.orchestrator import AcquisitionRunSummary, RunTerminalCode
from deepaha.acquisition.recipes import recipe_allows_url
from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import OpportunityDocumentRole, OpportunityReviewStatus
from deepaha.documents.models import Document, EvidenceRef
from deepaha.local_human_test.contracts import ItemStatus, RunMode
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.runs import BudgetExhausted, HumanTestRunService
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.opportunities.service import OpportunityResolutionService
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument
from deepaha.sources.models import Source, SourceEndpoint
from deepaha.sources.registry import SourceRegistryManifest


class BootstrapConfigurationError(ValueError):
    pass


class HumanTestAcquisitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActiveRecipeView:
    recipe_id: UUID
    source_id: UUID
    endpoint_id: UUID
    authority_name: str
    jurisdiction: str | None
    usage_role: SourceUsageRole
    official_url: str
    official_host: str
    allowed_hosts: tuple[str, ...]
    verified_at: datetime
    maximum_requests: int
    opportunity_type_hint: OpportunityTypeV02


@dataclass(frozen=True, slots=True)
class BootstrapReviewRequired:
    document_id: UUID
    recipe_id: UUID
    reason_codes: tuple[str, ...]
    candidate_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ProvisionalOpportunityView:
    opportunity_id: UUID
    public_id: str
    type: str
    canonical_title: str
    issuer_name: str
    jurisdiction: str | None
    status: str
    publication_status: str


@dataclass(frozen=True, slots=True)
class ProvisionalVersionView:
    version: int
    review_status: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ProvisionalTarget:
    opportunity: ProvisionalOpportunityView
    version: ProvisionalVersionView
    canonical_url: str
    evidence_ref_id: UUID


@dataclass(frozen=True, slots=True)
class AcquiredDocument:
    item_id: UUID
    document_id: UUID
    acquisition_evaluation_id: UUID
    source_id: UUID
    endpoint_id: UUID
    final_url: str
    title: str | None
    content_sha256: str
    mode: RunMode


@dataclass(frozen=True, slots=True)
class AcquisitionExecution:
    summary: AcquisitionRunSummary
    acquisition_evaluation_ids: tuple[UUID, ...]


class HumanAcquisitionRunner(Protocol):
    def run(self, recipe_id: UUID) -> AcquisitionExecution: ...


RunnerFactory = Callable[[Callable[[], object]], HumanAcquisitionRunner]


def build_active_recipe_views(
    recipes: Sequence[SourceRecipe],
    registry: SourceRegistryManifest,
) -> tuple[ActiveRecipeView, ...]:
    registry_by_source = {entry.source.source_id: entry for entry in registry.sources}
    views: list[ActiveRecipeView] = []
    for recipe in recipes:
        if not recipe.active:
            continue
        entry = registry_by_source.get(recipe.source_id)
        endpoint = next(
            (
                value
                for value in (() if entry is None else entry.endpoints)
                if value.endpoint_id == recipe.endpoint_id
            ),
            None,
        )
        if entry is None or endpoint is None:
            raise BootstrapConfigurationError("ACTIVE_RECIPE_REGISTRY_BINDING_MISSING")
        if recipe.opportunity_type_hint is None:
            raise BootstrapConfigurationError("ACTIVE_RECIPE_TYPE_HINT_MISSING")
        host = (urlsplit(str(endpoint.url)).hostname or "").lower().rstrip(".")
        if host not in recipe.allowed_hosts:
            raise BootstrapConfigurationError("ACTIVE_RECIPE_HOST_BINDING_INVALID")
        views.append(
            ActiveRecipeView(
                recipe_id=recipe.recipe_id,
                source_id=recipe.source_id,
                endpoint_id=recipe.endpoint_id,
                authority_name=entry.source.authority_name,
                jurisdiction=entry.source.jurisdiction,
                usage_role=recipe.usage_role,
                official_url=str(endpoint.url),
                official_host=host,
                allowed_hosts=recipe.allowed_hosts,
                verified_at=recipe.verified_at,
                maximum_requests=recipe.maximum_requests,
                opportunity_type_hint=recipe.opportunity_type_hint,
            )
        )
    return tuple(sorted(views, key=lambda value: value.recipe_id.int))


class HumanTestAcquisitionService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        run_service: HumanTestRunService,
        recipes: Sequence[SourceRecipe],
        registry: SourceRegistryManifest,
        live_runner_factory: RunnerFactory,
        replay_runner_factory: RunnerFactory,
    ) -> None:
        self._session_factory = session_factory
        self._run_service = run_service
        self._recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self._views = build_active_recipe_views(recipes, registry)
        self._live_runner_factory = live_runner_factory
        self._replay_runner_factory = replay_runner_factory

    def list_active_recipes(self) -> tuple[ActiveRecipeView, ...]:
        return self._views

    def acquire(
        self,
        item_id: UUID,
        mode: RunMode,
        *,
        worker_id: str,
    ) -> AcquiredDocument | None:
        with self._session_factory() as session:
            row = session.execute(
                select(LocalHumanTestItem, LocalHumanTestRun)
                .join(LocalHumanTestRun, LocalHumanTestItem.run_id == LocalHumanTestRun.run_id)
                .where(LocalHumanTestItem.item_id == item_id)
            ).one_or_none()
            if row is None:
                raise HumanTestAcquisitionError("LOCAL_HUMAN_TEST_ITEM_NOT_FOUND")
            item, run = row
            if RunMode(run.mode) is not mode:
                raise HumanTestAcquisitionError("RUN_MODE_MISMATCH")
            recipe_id = UUID(item.recipe_id)
            recipe = self._recipes.get(recipe_id)
            if recipe is None or not recipe.active:
                raise HumanTestAcquisitionError("ACTIVE_RECIPE_NOT_FOUND")
            run_id = run.run_id
            current = ItemStatus(item.status)

        if current is ItemStatus.CREATED:
            self._run_service.transition_item(
                item_id,
                expected=ItemStatus.CREATED,
                target=ItemStatus.ACQUIRING,
            )
        elif current is not ItemStatus.ACQUIRING:
            raise HumanTestAcquisitionError("ITEM_NOT_ACQUIRABLE")

        def reserve() -> object:
            return self._run_service.record_official_request(run_id, worker_id)

        factory = (
            self._live_runner_factory
            if mode is RunMode.LIVE_OFFICIAL
            else self._replay_runner_factory
        )
        try:
            callback = reserve if mode is RunMode.LIVE_OFFICIAL else _forbid_replay_fetch
            execution = factory(callback).run(recipe_id)
        except BudgetExhausted as error:
            self._run_service.transition_item(
                item_id,
                expected=ItemStatus.ACQUIRING,
                target=ItemStatus.PARTIAL_BUDGET_EXHAUSTED,
                error_code=str(error),
            )
            return None

        summary = execution.summary
        if summary.terminal_code is not RunTerminalCode.COMPLETE or summary.parsed_count < 1:
            target = (
                ItemStatus.PARTIAL_BUDGET_EXHAUSTED
                if summary.terminal_code is RunTerminalCode.REQUEST_BUDGET_EXHAUSTED
                else ItemStatus.ACQUISITION_REJECTED
            )
            self._run_service.transition_item(
                item_id,
                expected=ItemStatus.ACQUIRING,
                target=target,
                error_code=summary.terminal_code.value,
            )
            return None
        acquired = self._load_acquired_document(
            item_id=item_id,
            evaluation_ids=execution.acquisition_evaluation_ids,
            mode=mode,
        )
        if acquired is None:
            self._run_service.transition_item(
                item_id,
                expected=ItemStatus.ACQUIRING,
                target=ItemStatus.ACQUISITION_REJECTED,
                error_code="VALID_DOCUMENT_NOT_FOUND",
            )
            return None
        self._run_service.transition_item(
            item_id,
            expected=ItemStatus.ACQUIRING,
            target=ItemStatus.EXTRACTING,
            references={
                "source_id": acquired.source_id,
                "endpoint_id": acquired.endpoint_id,
                "acquisition_evaluation_id": acquired.acquisition_evaluation_id,
                "document_id": acquired.document_id,
            },
        )
        return acquired

    def _load_acquired_document(
        self,
        *,
        item_id: UUID,
        evaluation_ids: tuple[UUID, ...],
        mode: RunMode,
    ) -> AcquiredDocument | None:
        if not evaluation_ids:
            return None
        with self._session_factory() as session:
            row = session.execute(
                select(AcquisitionEvaluation, Document, RawArtifact)
                .join(Document, Document.artifact_id == AcquisitionEvaluation.artifact_id)
                .join(RawArtifact, RawArtifact.artifact_id == AcquisitionEvaluation.artifact_id)
                .where(
                    AcquisitionEvaluation.acquisition_evaluation_id.in_(evaluation_ids),
                    AcquisitionEvaluation.validation_status == ValidationStatus.VALID.value,
                )
                .order_by(AcquisitionEvaluation.evaluated_at.desc())
                .limit(1)
            ).one_or_none()
            if row is None:
                return None
            evaluation, document, artifact = row
            return AcquiredDocument(
                item_id=item_id,
                document_id=document.document_id,
                acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
                source_id=evaluation.source_id,
                endpoint_id=evaluation.endpoint_id,
                final_url=artifact.resolved_url,
                title=document.title,
                content_sha256=artifact.content_sha256,
                mode=mode,
            )


def _forbid_replay_fetch() -> object:
    raise HumanTestAcquisitionError("OFFICIAL_REPLAY_MUST_NOT_FETCH")


class ProvisionalOpportunityService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        recipes: Sequence[SourceRecipe],
        clock: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self._clock = clock
        self._resolution = OpportunityResolutionService(
            session_factory=session_factory,
            clock=clock,
            resolver_version="local-human-test-bootstrap-1.0.0",
            version_review_status=OpportunityReviewStatus.PENDING,
        )

    def create(
        self,
        *,
        document_id: UUID,
        recipe_id: UUID,
    ) -> ProvisionalTarget | BootstrapReviewRequired:
        recipe = self._recipes.get(recipe_id)
        if recipe is None or not recipe.active:
            return self._review(document_id, recipe_id, "ACTIVE_RECIPE_NOT_FOUND")
        if recipe.usage_role is not SourceUsageRole.PRIMARY_EVIDENCE:
            return self._review(document_id, recipe_id, "RECIPE_NOT_PRIMARY_EVIDENCE")
        if recipe.opportunity_type_hint is None:
            return self._review(document_id, recipe_id, "RECIPE_TYPE_HINT_MISSING")

        with self._session_factory() as session:
            row = session.execute(
                select(Document, RawArtifact, Source, SourceEndpoint)
                .join(RawArtifact, RawArtifact.artifact_id == Document.artifact_id)
                .join(Source, Source.source_id == RawArtifact.source_id)
                .join(
                    SourceEndpoint,
                    (SourceEndpoint.source_id == Source.source_id)
                    & (SourceEndpoint.endpoint_id == recipe.endpoint_id),
                )
                .where(Document.document_id == document_id)
            ).one_or_none()
            if row is None:
                return self._review(document_id, recipe_id, "DOCUMENT_BINDING_MISSING")
            document, artifact, source, endpoint = row
            reasons = self._preflight_reasons(
                recipe=recipe,
                document=document,
                artifact=artifact,
                source=source,
                endpoint=endpoint,
            )
            evaluation = session.scalar(
                select(AcquisitionEvaluation)
                .where(
                    AcquisitionEvaluation.artifact_id == artifact.artifact_id,
                    AcquisitionEvaluation.source_id == source.source_id,
                    AcquisitionEvaluation.endpoint_id == endpoint.endpoint_id,
                    AcquisitionEvaluation.validation_status == ValidationStatus.VALID.value,
                )
                .order_by(AcquisitionEvaluation.evaluated_at.desc())
                .limit(1)
            )
            if evaluation is None:
                reasons.append("ACQUISITION_NOT_VALID")
            evidence_ref_id = session.scalar(
                select(EvidenceRef.evidence_ref_id)
                .where(EvidenceRef.document_id == document_id)
                .order_by(EvidenceRef.evidence_ref_id)
                .limit(1)
            )
            if evidence_ref_id is None:
                reasons.append("DOCUMENT_EVIDENCE_MISSING")
            if reasons or evidence_ref_id is None:
                return BootstrapReviewRequired(
                    document_id=document_id,
                    recipe_id=recipe_id,
                    reason_codes=tuple(sorted(set(reasons))),
                )
            title = document.title.strip() if document.title is not None else ""
            canonical_url = artifact.resolved_url
            command = ResolutionDocument(
                document_id=document_id,
                source_id=source.source_id,
                source_tier=SourceTier(source.tier),
                evidence_ref_id=evidence_ref_id,
                role=OpportunityDocumentRole.PRIMARY_NOTICE,
                canonical_url=canonical_url,
                external_id=None,
                references_document_ids=(),
                effective_at=document.published_at or document.created_at,
                facts=OpportunityPatch(
                    canonical_title=title,
                    type=recipe.opportunity_type_hint,
                    issuer_name=source.authority_name,
                    jurisdiction=source.jurisdiction,
                    status=OpportunityStatus.UNKNOWN,
                    published_at=document.published_at,
                    application_url=canonical_url,
                ),
            )

        result = self._resolution.resolve(command)
        if result.opportunity_id is None or result.version is None:
            return BootstrapReviewRequired(
                document_id=document_id,
                recipe_id=recipe_id,
                reason_codes=result.reason_codes or ("RESOLUTION_REVIEW_REQUIRED",),
                candidate_id=result.candidate_id,
            )
        with self._session_factory() as session:
            opportunity = session.get(Opportunity, result.opportunity_id)
            version = session.get(OpportunityVersion, (result.opportunity_id, result.version))
            if opportunity is None or version is None:
                raise RuntimeError("PROVISIONAL_OPPORTUNITY_PERSISTENCE_MISSING")
            return ProvisionalTarget(
                opportunity=ProvisionalOpportunityView(
                    opportunity_id=opportunity.opportunity_id,
                    public_id=opportunity.public_id,
                    type=opportunity.type,
                    canonical_title=opportunity.canonical_title,
                    issuer_name=opportunity.issuer_name,
                    jurisdiction=opportunity.jurisdiction,
                    status=opportunity.status,
                    publication_status=opportunity.publication_status,
                ),
                version=ProvisionalVersionView(
                    version=version.version,
                    review_status=version.review_status,
                    content_sha256=version.content_sha256,
                ),
                canonical_url=canonical_url,
                evidence_ref_id=evidence_ref_id,
            )

    @staticmethod
    def _review(document_id: UUID, recipe_id: UUID, code: str) -> BootstrapReviewRequired:
        return BootstrapReviewRequired(
            document_id=document_id,
            recipe_id=recipe_id,
            reason_codes=(code,),
        )

    @staticmethod
    def _preflight_reasons(
        *,
        recipe: SourceRecipe,
        document: Document,
        artifact: RawArtifact,
        source: Source,
        endpoint: SourceEndpoint,
    ) -> list[str]:
        reasons: list[str] = []
        if document.title is None or not document.title.strip():
            reasons.append("DOCUMENT_TITLE_MISSING")
        if not source.authority_name.strip():
            reasons.append("SOURCE_ISSUER_MISSING")
        if (
            source.source_id != recipe.source_id
            or SourceTier(source.tier) is not SourceTier.OFFICIAL_PRIMARY
        ):
            reasons.append("SOURCE_NOT_OFFICIAL_PRIMARY")
        if not endpoint.active or endpoint.policy_version != recipe.endpoint_policy_version:
            reasons.append("ENDPOINT_POLICY_NOT_ACTIVE")
        if not artifact.resolved_url or not recipe_allows_url(recipe, artifact.resolved_url):
            reasons.append("FINAL_URL_NOT_STABLE_OR_ALLOWED")
        return reasons


__all__ = [
    "AcquiredDocument",
    "AcquisitionExecution",
    "ActiveRecipeView",
    "BootstrapConfigurationError",
    "BootstrapReviewRequired",
    "HumanAcquisitionRunner",
    "HumanTestAcquisitionError",
    "HumanTestAcquisitionService",
    "ProvisionalOpportunityService",
    "ProvisionalOpportunityView",
    "ProvisionalTarget",
    "ProvisionalVersionView",
    "RunnerFactory",
    "build_active_recipe_views",
]
