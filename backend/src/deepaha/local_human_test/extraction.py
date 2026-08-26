from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.artifacts.object_store import ObjectIntegrityError, ObjectStore
from deepaha.contracts.phase9b import (
    DocumentBlockType,
    EgressBlockClassificationSchemaV08,
    EgressDecisionSchemaV08,
    EgressDecisionValue,
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    ExtractionRunStatus,
    ExtractionTargetScope,
    ExtractorKind,
    ModelCallIntentSchemaV08,
    ModelRouteClass,
    ModelTaskSpecSchemaV08,
    ProviderEgressPolicySnapshotSchemaV08,
    RetentionClass,
    SourceEgressPolicySnapshotSchemaV08,
)
from deepaha.documents.models import Document, DocumentBlock
from deepaha.local_human_test.contracts import (
    ExternalCallBudget,
    ItemStatus,
    ProviderConfigSnapshot,
)
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.runs import BudgetExhausted, HumanTestRunService
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.egress import EgressRepository
from deepaha.p9b.facts import FactLifecycleService
from deepaha.p9b.gateway import GatewayExecutor
from deepaha.p9b.hashing import (
    canonical_json_bytes,
    extraction_evidence_binding_hash,
    extraction_input_block_set_hash,
    model_invocation_identity,
    model_request_hash,
)
from deepaha.p9b.models import (
    EgressBlockClassification,
    ExtractionCandidate,
    ExtractionRun,
    ModelCall,
    ModelTaskSpec,
    SourceBundleMember,
    SourceBundleRevision,
)
from deepaha.p9b.provenance import BundleMemberSpec, BundleService
from deepaha.p9b.provider import ProviderInvocation, ProviderMessage

EXTRACTION_SCHEMA_VERSION = "0.8.0"

FactFieldName = Literal[
    "canonical_title",
    "type",
    "issuer_name",
    "jurisdiction",
    "status",
    "published_at",
    "application_window",
    "application_deadline",
    "application_url",
    "attachment_urls",
    "locations",
    "recruitment_count",
    "applicant_scope",
    "education_requirements",
    "major_requirements",
    "age_requirements",
    "experience_requirements",
    "credential_requirements",
    "household_registration_requirements",
]

RuleFieldName = Literal[
    "education",
    "major",
    "age",
    "experience",
    "credential",
    "household_registration",
    "applicant_scope",
]


class ExtractionValidationError(ValueError):
    """A model response cannot become a persisted human-review candidate."""


class ModelFactCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field_name: FactFieldName
    raw_value: JsonValue | None
    normalized_value_candidate: JsonValue | None
    evidence_block_ids: tuple[UUID, ...] = Field(min_length=1)
    confidence: Annotated[float, Field(ge=0, le=1)] | None
    abstained: bool
    reason_code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Z][A-Z0-9_]*$")

    @model_validator(mode="after")
    def require_abstention_shape(self) -> Self:
        if len(self.evidence_block_ids) != len(set(self.evidence_block_ids)):
            raise ValueError("fact evidence block IDs must be unique")
        if self.abstained:
            if self.normalized_value_candidate is not None:
                raise ValueError("abstention forbids a normalized value")
            if not self.reason_code.startswith("UNKNOWN_"):
                raise ValueError("abstention requires an UNKNOWN reason code")
        elif self.normalized_value_candidate is None:
            raise ValueError("known fact requires a normalized value")
        return self


class ModelRuleCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field_name: RuleFieldName
    expression_candidate: JsonValue | None
    evidence_block_ids: tuple[UUID, ...] = Field(min_length=1)
    confidence: Annotated[float, Field(ge=0, le=1)] | None
    abstained: bool
    reason_code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Z][A-Z0-9_]*$")

    @model_validator(mode="after")
    def require_abstention_shape(self) -> Self:
        if len(self.evidence_block_ids) != len(set(self.evidence_block_ids)):
            raise ValueError("rule evidence block IDs must be unique")
        if self.abstained:
            if self.expression_candidate is not None:
                raise ValueError("rule abstention forbids an expression")
            if not self.reason_code.startswith("UNKNOWN_"):
                raise ValueError("rule abstention requires an UNKNOWN reason code")
        elif self.expression_candidate is None:
            raise ValueError("known rule candidate requires an expression")
        return self


class ModelExtractionEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.8.0"]
    facts: tuple[ModelFactCandidate, ...] = Field(min_length=1)
    rules: tuple[ModelRuleCandidate, ...]
    uncertainties: tuple[str, ...]

    @model_validator(mode="after")
    def require_uncertainty_shape(self) -> Self:
        if any(not value.strip() or len(value) > 500 for value in self.uncertainties):
            raise ValueError("uncertainties must contain bounded non-empty text")
        if self.rules:
            raise ValueError("model rule candidates are not eligible before fact verification")
        return self


@dataclass(frozen=True, slots=True)
class MinimizedExtractionBlock:
    block_id: UUID
    evidence_ref_id: UUID
    block_hash: str
    evidence_binding_hash: str
    block_type: str
    ordinal: int
    content: str

    def __post_init__(self) -> None:
        if (
            len(self.block_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.block_hash)
            or len(self.evidence_binding_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.evidence_binding_hash)
            or self.ordinal < 1
            or not self.block_type
            or not self.content.strip()
        ):
            raise ValueError("minimized extraction block is invalid")


@dataclass(frozen=True, slots=True)
class ExtractionPrompt:
    blocks: tuple[MinimizedExtractionBlock, ...]
    messages: tuple[ProviderMessage, ...]


_SYSTEM_PROMPT = (
    "You extract only explicitly supported opportunity facts from official-source blocks. "
    "Return one JSON object using schema_version 0.8.0 with exactly these keys: "
    "schema_version, facts, rules, uncertainties. Each fact must contain field_name, "
    "raw_value, normalized_value_candidate, evidence_block_ids, confidence, abstained, "
    "reason_code. The rules value must be an empty array because rule generation occurs "
    "only after human fact verification. Every evidence_block_ids "
    "value must name an input block. Never infer an unsupported fact. Use abstained=true, "
    "a null candidate value, and an UNKNOWN_ reason when official text is ambiguous. "
    "Do not include prose outside JSON."
)


def _input_token_upper_bound(messages: tuple[ProviderMessage, ...]) -> int:
    # One UTF-8 byte per token is deliberately conservative for mixed Chinese/ASCII input.
    return sum(len(message.content.encode("utf-8")) for message in messages)


def prepare_extraction_prompt(
    *,
    opportunity_id: UUID,
    opportunity_version: int,
    blocks: tuple[MinimizedExtractionBlock, ...],
    max_input_tokens: int,
) -> ExtractionPrompt:
    if opportunity_version < 1 or max_input_tokens < 1 or not blocks:
        raise ExtractionValidationError("MODEL_INPUT_BUDGET_EXCEEDED")
    ordered = tuple(sorted(blocks, key=lambda block: (block.ordinal, block.block_id.int)))
    if len({block.block_id for block in ordered}) != len(ordered):
        raise ExtractionValidationError("DUPLICATE_INPUT_BLOCK")
    selected: list[MinimizedExtractionBlock] = []
    for block in ordered:
        candidate = (*selected, block)
        messages = _messages(opportunity_id, opportunity_version, candidate)
        if _input_token_upper_bound(messages) > max_input_tokens:
            break
        selected.append(block)
    if not selected:
        raise ExtractionValidationError("MODEL_INPUT_BUDGET_EXCEEDED")
    return ExtractionPrompt(
        blocks=tuple(selected),
        messages=_messages(opportunity_id, opportunity_version, tuple(selected)),
    )


def build_extraction_messages(
    *,
    opportunity_id: UUID,
    opportunity_version: int,
    blocks: tuple[MinimizedExtractionBlock, ...],
    max_input_tokens: int,
) -> tuple[ProviderMessage, ...]:
    return prepare_extraction_prompt(
        opportunity_id=opportunity_id,
        opportunity_version=opportunity_version,
        blocks=blocks,
        max_input_tokens=max_input_tokens,
    ).messages


def _messages(
    opportunity_id: UUID,
    opportunity_version: int,
    blocks: tuple[MinimizedExtractionBlock, ...],
) -> tuple[ProviderMessage, ...]:
    payload = {
        "target": {
            "target_scope": "OPPORTUNITY",
            "opportunity_id": str(opportunity_id),
            "opportunity_version": opportunity_version,
        },
        "blocks": [
            {
                "block_id": str(block.block_id),
                "block_hash": block.block_hash,
                "block_type": block.block_type,
                "ordinal": block.ordinal,
                "content": block.content,
            }
            for block in blocks
        ],
    }
    return (
        ProviderMessage(role="system", content=_SYSTEM_PROMPT),
        ProviderMessage(role="user", content=canonical_json_bytes(payload).decode("utf-8")),
    )


def parse_provider_envelope(raw_response: bytes) -> tuple[str, ModelExtractionEnvelope]:
    try:
        outer = json.loads(raw_response)
        if not isinstance(outer, dict):
            raise TypeError
        response_id = outer["id"]
        choices = outer["choices"]
        if not isinstance(response_id, str) or not response_id.strip():
            raise TypeError
        if not isinstance(choices, list) or len(choices) != 1:
            raise TypeError
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
            raise TypeError
        message = choice.get("message")
        if (
            not isinstance(message, dict)
            or message.get("role") != "assistant"
            or not isinstance(message.get("content"), str)
        ):
            raise TypeError
        envelope = ModelExtractionEnvelope.model_validate_json(message["content"])
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtractionValidationError("MODEL_OUTPUT_INVALID") from error
    return response_id, envelope


def validate_candidate_bindings(
    envelope: ModelExtractionEnvelope,
    *,
    blocks: tuple[MinimizedExtractionBlock, ...],
) -> ModelExtractionEnvelope:
    allowed = {block.block_id for block in blocks}
    fact_fields = [fact.field_name for fact in envelope.facts]
    if len(fact_fields) != len(set(fact_fields)):
        raise ExtractionValidationError("DUPLICATE_FACT_FIELD")
    rule_fields = [rule.field_name for rule in envelope.rules]
    if len(rule_fields) != len(set(rule_fields)):
        raise ExtractionValidationError("DUPLICATE_RULE_FIELD")
    evidence_sets = [fact.evidence_block_ids for fact in envelope.facts]
    evidence_sets.extend(rule.evidence_block_ids for rule in envelope.rules)
    for evidence_block_ids in evidence_sets:
        if not set(evidence_block_ids) <= allowed:
            raise ExtractionValidationError("EVIDENCE_BINDING_INVALID")
    return envelope


class ExtractionConfigurationError(ValueError):
    """The frozen local run configuration cannot authorize model egress."""


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    item_id: UUID
    status: ItemStatus
    model_call_id: UUID | None
    extraction_run_id: UUID | None
    candidate_ids: tuple[UUID, ...]
    uncertainty_count: int


@dataclass(frozen=True, slots=True)
class _PreparedExtraction:
    item_id: UUID
    run_id: UUID
    reviewer_id: UUID
    opportunity_id: UUID
    opportunity_version: int
    source_bundle_revision_id: UUID
    prompt: ExtractionPrompt
    intent: ModelCallIntentSchemaV08


class P9BExtractionCoordinator:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        gateway: GatewayExecutor,
        object_store: ObjectStore,
        response_bucket: str,
        run_service: HumanTestRunService,
        worker_id: str,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway
        self._object_store = object_store
        self._response_bucket = response_bucket
        self._run_service = run_service
        self._worker_id = worker_id

    def extract(self, item_id: UUID) -> ExtractionOutcome:
        try:
            prepared = self._prepare(item_id)
            registered = self._gateway.register(
                intent=prepared.intent,
                messages=prepared.prompt.messages,
            )
            self._run_service.record_item_llm_call(
                item_id,
                registered.model_call_id,
                self._worker_id,
            )
        except ExtractionConfigurationError as error:
            code = str(error)
            return self._fail(
                item_id,
                target=ItemStatus.FAILED_CONFIG,
                error_code=code if code.isupper() else "EXTRACTION_CONFIGURATION_INVALID",
            )
        except ValidationError:
            return self._fail(
                item_id,
                target=ItemStatus.FAILED_CONFIG,
                error_code="EXTRACTION_CONFIGURATION_INVALID",
            )
        except ExtractionValidationError as error:
            code = str(error)
            return self._fail(
                item_id,
                target=ItemStatus.FAILED_CONFIG,
                error_code=code if code.isupper() else "EXTRACTION_INPUT_INVALID",
            )
        except BudgetExhausted:
            return self._fail(
                item_id,
                target=ItemStatus.PARTIAL_BUDGET_EXHAUSTED,
                error_code="LLM_CALL_BUDGET_EXHAUSTED",
            )

        ledger = self._gateway.execute(
            intent=registered,
            messages=prepared.prompt.messages,
        )
        if ledger["terminal_disposition"] == "PROVIDER_OUTCOME_UNKNOWN":
            return self._fail(
                item_id,
                target=ItemStatus.UNKNOWN_OUTCOME,
                error_code="PROVIDER_OUTCOME_UNKNOWN",
                model_call_id=registered.model_call_id,
            )
        if ledger["status"] != "SUCCEEDED":
            return self._fail(
                item_id,
                target=ItemStatus.FAILED,
                error_code="MODEL_CALL_TERMINAL_FAILED",
                model_call_id=registered.model_call_id,
            )

        try:
            raw = self._read_audited_response(ledger)
            response_id, envelope = parse_provider_envelope(raw)
            validated = validate_candidate_bindings(
                envelope,
                blocks=prepared.prompt.blocks,
            )
        except (ExtractionValidationError, ObjectIntegrityError) as error:
            code = str(error)
            target = (
                ItemStatus.EVIDENCE_BINDING_INVALID
                if code == "EVIDENCE_BINDING_INVALID"
                else ItemStatus.MODEL_OUTPUT_INVALID
            )
            return self._fail(
                item_id,
                target=target,
                error_code=code if code.isupper() else "MODEL_OUTPUT_INVALID",
                model_call_id=registered.model_call_id,
            )
        except ValidationError:
            return self._fail(
                item_id,
                target=ItemStatus.MODEL_OUTPUT_INVALID,
                error_code="MODEL_OUTPUT_INVALID",
                model_call_id=registered.model_call_id,
            )

        extraction_run_id, candidate_ids = self._persist_candidates(
            prepared=prepared,
            model_call_id=registered.model_call_id,
            response_id=response_id,
            envelope=validated,
        )
        self._run_service.transition_item(
            item_id,
            expected=ItemStatus.EXTRACTING,
            target=ItemStatus.FACT_REVIEW,
            references={
                "source_bundle_revision_id": prepared.source_bundle_revision_id,
                "extraction_run_id": extraction_run_id,
                "model_call_id": registered.model_call_id,
            },
        )
        return ExtractionOutcome(
            item_id=item_id,
            status=ItemStatus.FACT_REVIEW,
            model_call_id=registered.model_call_id,
            extraction_run_id=extraction_run_id,
            candidate_ids=candidate_ids,
            uncertainty_count=len(validated.uncertainties),
        )

    def _prepare(self, item_id: UUID) -> _PreparedExtraction:
        with self._session_factory.begin() as session:
            row = session.execute(
                select(LocalHumanTestItem, LocalHumanTestRun)
                .join(LocalHumanTestRun, LocalHumanTestItem.run_id == LocalHumanTestRun.run_id)
                .where(LocalHumanTestItem.item_id == item_id)
                .with_for_update()
            ).one_or_none()
            if row is None:
                raise ExtractionConfigurationError("LOCAL_HUMAN_TEST_ITEM_NOT_FOUND")
            item, run = row
            if ItemStatus(item.status) is not ItemStatus.EXTRACTING:
                raise ExtractionConfigurationError("ITEM_NOT_EXTRACTING")
            if item.document_id is None or item.opportunity_id is None:
                raise ExtractionConfigurationError("EXTRACTION_TARGET_INCOMPLETE")
            config = ProviderConfigSnapshot.model_validate(run.provider_config_snapshot)
            if (
                not config.zero_retention
                or config.training_use
                or config.provider_region == "unknown"
            ):
                raise ExtractionConfigurationError("PROVIDER_EGRESS_POLICY_NOT_CONFIRMED")
            budget = ExternalCallBudget.model_validate(run.budget)
            opportunity = session.get(Opportunity, item.opportunity_id)
            if opportunity is None or opportunity.current_version is None:
                raise ExtractionConfigurationError("OPPORTUNITY_VERSION_MISSING")
            version = session.get(
                OpportunityVersion,
                (opportunity.opportunity_id, opportunity.current_version),
            )
            if version is None or version.review_status != "PENDING":
                raise ExtractionConfigurationError("PROVISIONAL_OPPORTUNITY_REQUIRED")
            revision = self._load_or_create_revision(
                session,
                item=item,
                opportunity=opportunity,
                version=version,
            )
            blocks = tuple(
                MinimizedExtractionBlock(
                    block_id=block.block_id,
                    evidence_ref_id=block.evidence_ref_id,
                    block_hash=block.block_hash,
                    evidence_binding_hash=block.evidence_binding_hash,
                    block_type=block.block_type,
                    ordinal=block.ordinal,
                    content=block.canonical_text_or_value,
                )
                for block in session.scalars(
                    select(DocumentBlock)
                    .where(DocumentBlock.document_id == item.document_id)
                    .order_by(DocumentBlock.ordinal, DocumentBlock.block_id)
                )
            )
            prompt = prepare_extraction_prompt(
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=version.version,
                blocks=blocks,
                max_input_tokens=budget.max_input_tokens,
            )
            intent = self._persist_authority(
                session,
                item=item,
                run=run,
                config=config,
                budget=budget,
                revision=revision,
                prompt=prompt,
            )
            return _PreparedExtraction(
                item_id=item.item_id,
                run_id=run.run_id,
                reviewer_id=run.created_by_reviewer_id,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=version.version,
                source_bundle_revision_id=revision.source_bundle_revision_id,
                prompt=prompt,
                intent=intent,
            )

    def _load_or_create_revision(
        self,
        session: Session,
        *,
        item: LocalHumanTestItem,
        opportunity: Opportunity,
        version: OpportunityVersion,
    ) -> SourceBundleRevision:
        if item.source_bundle_revision_id is not None:
            revision = session.get(SourceBundleRevision, item.source_bundle_revision_id)
            member_exists = session.scalar(
                select(SourceBundleMember.source_bundle_member_id).where(
                    SourceBundleMember.source_bundle_revision_id == item.source_bundle_revision_id,
                    SourceBundleMember.document_id == item.document_id,
                )
            )
            if revision is None or revision.status != "FROZEN" or member_exists is None:
                raise ExtractionConfigurationError("SOURCE_BUNDLE_BINDING_INVALID")
            return revision
        if item.acquisition_evaluation_id is None or item.document_id is None:
            raise ExtractionConfigurationError("ACQUISITION_LINEAGE_INCOMPLETE")
        evaluation = session.get(AcquisitionEvaluation, item.acquisition_evaluation_id)
        document = session.get(Document, item.document_id)
        if evaluation is None or document is None:
            raise ExtractionConfigurationError("ACQUISITION_LINEAGE_INCOMPLETE")
        runs = tuple(
            session.scalars(
                select(AcquisitionRun).where(
                    AcquisitionRun.recipe_id == UUID(item.recipe_id),
                    AcquisitionRun.source_id == evaluation.source_id,
                    AcquisitionRun.endpoint_id == evaluation.endpoint_id,
                )
            )
        )
        matching_runs = tuple(
            run
            for run in runs
            if any(
                attempt.get("capture_observation_id") == str(evaluation.observation_id)
                and attempt.get("acquisition_evaluation_id")
                == str(evaluation.acquisition_evaluation_id)
                and attempt.get("raw_artifact_id") == str(evaluation.artifact_id)
                for attempt in run.strategy_attempts
            )
        )
        if len(matching_runs) != 1:
            raise ExtractionConfigurationError("ACQUISITION_RUN_BINDING_AMBIGUOUS")
        service = BundleService(session)
        revision = service.create_revision(
            opportunity_id=opportunity.opportunity_id,
            opportunity_version=version.version,
            effective_as_of=document.created_at,
            members=[
                BundleMemberSpec(
                    document_id=document.document_id,
                    capture_observation_id=evaluation.observation_id,
                    acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
                    acquisition_run_id=matching_runs[0].acquisition_run_id,
                    member_role="PRIMARY_NOTICE",
                    precedence=100,
                    effective_from=document.published_at,
                    effective_to=None,
                )
            ],
        )
        service.freeze_revision(
            revision.source_bundle_revision_id,
            frozen_at=document.created_at,
        )
        item.source_bundle_revision_id = revision.source_bundle_revision_id
        session.flush()
        return revision

    def _persist_authority(
        self,
        session: Session,
        *,
        item: LocalHumanTestItem,
        run: LocalHumanTestRun,
        config: ProviderConfigSnapshot,
        budget: ExternalCallBudget,
        revision: SourceBundleRevision,
        prompt: ExtractionPrompt,
    ) -> ModelCallIntentSchemaV08:
        task_name = f"human-extract-{item.item_id.hex}"
        existing_calls = tuple(
            session.scalars(
                select(ModelCall)
                .where(ModelCall.task_spec_name == task_name)
                .order_by(ModelCall.registered_at, ModelCall.model_call_id)
            )
        )
        if len(existing_calls) > 1:
            raise ExtractionConfigurationError("MULTIPLE_MODEL_CALLS_FOR_ITEM")
        if existing_calls:
            return self._intent_from_model_call(existing_calls[0])

        database_now = session.scalar(select(text("clock_timestamp()")))
        assert isinstance(database_now, datetime)
        task = self._ensure_task(
            session,
            task_name=task_name,
            budget=budget,
            block_types=tuple(block.block_type for block in prompt.blocks),
            created_at=database_now,
        )
        repository = EgressRepository(session)
        classification_version = "local-official-public-v1"
        for block in prompt.blocks:
            existing = session.scalar(
                select(EgressBlockClassification).where(
                    EgressBlockClassification.block_id == block.block_id,
                    EgressBlockClassification.block_hash == block.block_hash,
                    EgressBlockClassification.classification_version == classification_version,
                )
            )
            if existing is None:
                repository.persist_block_classification(
                    EgressBlockClassificationSchemaV08(
                        classification_id=uuid7(),
                        block_id=block.block_id,
                        block_hash=block.block_hash,
                        classification_version=classification_version,
                        classifications=["PUBLIC_OFFICIAL_GENERAL"],
                        contains_user_data=False,
                        classifier_identity="system:local-official-source-v1",
                        created_at=database_now,
                    )
                )

        valid_until = database_now + timedelta(hours=1)
        source_snapshot_id = f"human-source-{uuid7().hex}"
        source_snapshot_hash = model_request_hash(
            {
                "snapshot_id": source_snapshot_id,
                "revision_id": str(revision.source_bundle_revision_id),
                "allows_egress": True,
                "valid_until": valid_until.isoformat(),
            }
        )
        provider_snapshot_id = f"human-provider-{uuid7().hex}"
        provider_snapshot_hash = model_request_hash(
            {
                "snapshot_id": provider_snapshot_id,
                "provider": config.provider,
                "base_url": str(config.base_url).rstrip("/"),
                "region": config.provider_region,
                "zero_retention": config.zero_retention,
                "training_use": config.training_use,
                "supports_idempotency": config.supports_idempotency,
                "valid_until": valid_until.isoformat(),
            }
        )
        actor = f"human:{run.created_by_reviewer_id}"
        repository.persist_source_policy(
            SourceEgressPolicySnapshotSchemaV08(
                snapshot_id=source_snapshot_id,
                snapshot_hash=source_snapshot_hash,
                source_bundle_revision_id=revision.source_bundle_revision_id,
                allows_egress=True,
                valid_from=database_now,
                valid_until=valid_until,
                recorded_by=actor,
                created_at=database_now,
            )
        )
        repository.persist_provider_policy(
            ProviderEgressPolicySnapshotSchemaV08(
                snapshot_id=provider_snapshot_id,
                snapshot_hash=provider_snapshot_hash,
                provider=config.provider,
                region=config.provider_region,
                active=True,
                zero_retention=config.zero_retention,
                training_use=config.training_use,
                supports_idempotency=config.supports_idempotency,
                allowed_classifications=["PUBLIC_OFFICIAL_GENERAL"],
                retention_class=RetentionClass.ZERO_RETENTION,
                valid_from=database_now,
                valid_until=valid_until,
                recorded_by=actor,
                created_at=database_now,
            )
        )
        model_call_id = uuid7()
        identity = model_invocation_identity(
            ProviderInvocation(
                model_call_id=model_call_id,
                attempt_id=uuid7(),
                provider=config.provider,
                model_id=config.model_id,
                model_snapshot=config.model_snapshot,
                messages=prompt.messages,
                output_schema_version=task.output_schema_version,
                max_output_tokens=task.max_output_tokens,
                temperature=0.0,
                top_p=1.0,
                seed=0,
                timeout_ms=task.timeout_ms,
                idempotency_key=None,
            )
        )
        block_ids = [block.block_id for block in prompt.blocks]
        block_hashes = [block.block_hash for block in prompt.blocks]
        decision = EgressDecisionSchemaV08(
            egress_decision_id=uuid7(),
            task_spec_name=task.task_name,
            task_spec_version=task.task_version,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            target_scope=ExtractionTargetScope.OPPORTUNITY,
            opportunity_id=revision.opportunity_id,
            opportunity_version=revision.opportunity_version,
            opportunity_unit_id=None,
            opportunity_unit_version_id=None,
            input_block_ids=block_ids,
            input_block_hashes=block_hashes,
            data_classification_version=classification_version,
            minimizer_version="local-block-prefix-v1",
            redactor_version="public-official-no-redaction-v1",
            source_policy_snapshot_id=source_snapshot_id,
            source_policy_snapshot_hash=source_snapshot_hash,
            provider_policy_snapshot_id=provider_snapshot_id,
            provider_policy_snapshot_hash=provider_snapshot_hash,
            provider=config.provider,
            provider_region=config.provider_region,
            original_input_hash=model_request_hash(
                {
                    "input_block_ids": [str(value) for value in block_ids],
                    "input_block_hashes": block_hashes,
                }
            ),
            actual_payload_hash=identity.actual_payload_hash,
            decision=EgressDecisionValue.ALLOW,
            actor_type="HUMAN",
            actor_identity=actor,
            reason_codes=["HUMAN_CONFIRMED_PUBLIC_OFFICIAL_EGRESS"],
            created_at=database_now,
            expires_at=database_now + timedelta(minutes=5),
        )
        repository.persist_decision(decision)
        return ModelCallIntentSchemaV08(
            model_call_id=model_call_id,
            task_spec_name=task.task_name,
            task_spec_version=task.task_version,
            provider=config.provider,
            model_id=config.model_id,
            model_snapshot=config.model_snapshot,
            adapter_name="openai-compatible",
            adapter_version="1.0.0",
            runtime_version="python-3.14",
            canonical_request_hash=identity.canonical_request_hash,
            canonical_message_hashes=list(identity.canonical_message_hashes),
            input_block_ids=block_ids,
            input_block_hashes=block_hashes,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            target_scope=ExtractionTargetScope.OPPORTUNITY,
            opportunity_id=revision.opportunity_id,
            opportunity_version=revision.opportunity_version,
            opportunity_unit_id=None,
            opportunity_unit_version_id=None,
            unit_segmentation_version=None,
            prompt_version="local-human-extraction-prompt-v1",
            output_schema_version=task.output_schema_version,
            parser_version="local-human-extraction-parser-v1",
            contract_version="p9b-v0.8.0",
            temperature=0.0,
            top_p=1.0,
            seed=0,
            egress_decision_id=decision.egress_decision_id,
            validation_pipeline_version="local-human-extraction-validation-v1",
            retention_class=RetentionClass.ZERO_RETENTION,
            registered_at=database_now,
        )

    @staticmethod
    def _ensure_task(
        session: Session,
        *,
        task_name: str,
        budget: ExternalCallBudget,
        block_types: tuple[str, ...],
        created_at: datetime,
    ) -> ModelTaskSpec:
        existing = session.scalar(
            select(ModelTaskSpec).where(
                ModelTaskSpec.task_name == task_name,
                ModelTaskSpec.task_version == "v1",
            )
        )
        if existing is not None:
            expected_types = sorted(set(block_types))
            if (
                existing.max_input_tokens != budget.max_input_tokens
                or existing.max_output_tokens != budget.max_output_tokens
                or existing.timeout_ms != budget.timeout_seconds * 1000
                or sorted(existing.allowed_input_block_types) != expected_types
            ):
                raise ExtractionConfigurationError("MODEL_TASK_SPEC_CONFLICT")
            return existing
        contract = ModelTaskSpecSchemaV08(
            model_task_spec_id=uuid7(),
            task_name=task_name,
            task_version="v1",
            route_class=ModelRouteClass.R2_BALANCED_REASON,
            allowed_input_block_types=[
                DocumentBlockType(value) for value in sorted(set(block_types))
            ],
            output_schema_version="local-human-extraction-v1",
            max_input_tokens=budget.max_input_tokens,
            max_output_tokens=budget.max_output_tokens,
            evidence_required=True,
            abstention_allowed=True,
            risk_class="HIGH_IMPACT_CANDIDATE",
            provider_capabilities=["ZERO_RETENTION"],
            egress_policy_id="local-human-public-official-v1",
            timeout_ms=budget.timeout_seconds * 1000,
            max_attempts=2,
            initial_backoff_ms=250,
            backoff_multiplier=2.0,
            max_backoff_ms=1_000,
            max_concurrency=1,
            max_batch_size=1,
            fallback_policy="DISABLED",
            max_fallbacks=0,
            created_at=created_at,
        )
        return EgressRepository(session).persist_task_spec(contract)

    @staticmethod
    def _intent_from_model_call(call: ModelCall) -> ModelCallIntentSchemaV08:
        return ModelCallIntentSchemaV08.model_validate(
            {name: getattr(call, name) for name in ModelCallIntentSchemaV08.model_fields}
        )

    def _read_audited_response(self, ledger: dict[str, object]) -> bytes:
        if ledger.get("raw_response_reference_kind") != "INTERNAL_OBJECT":
            raise ExtractionValidationError("MODEL_OUTPUT_INVALID")
        if ledger.get("raw_response_storage_bucket") != self._response_bucket:
            raise ExtractionValidationError("MODEL_OUTPUT_INVALID")
        key = ledger.get("raw_response_object_key")
        digest = ledger.get("raw_response_sha256")
        if not isinstance(key, str) or not isinstance(digest, str):
            raise ExtractionValidationError("MODEL_OUTPUT_INVALID")
        raw = self._object_store.get_bytes(key=key)
        if sha256(raw).hexdigest() != digest:
            raise ExtractionValidationError("MODEL_OUTPUT_INVALID")
        return raw

    def _persist_candidates(
        self,
        *,
        prepared: _PreparedExtraction,
        model_call_id: UUID,
        response_id: str,
        envelope: ModelExtractionEnvelope,
    ) -> tuple[UUID, tuple[UUID, ...]]:
        producer_identity = f"model-call:{model_call_id}"
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(ExtractionRun).where(
                    ExtractionRun.source_bundle_revision_id == prepared.source_bundle_revision_id,
                    ExtractionRun.producer_identity == producer_identity,
                )
            )
            if existing is not None:
                persisted_candidate_ids = tuple(
                    session.scalars(
                        select(ExtractionCandidate.candidate_id)
                        .where(ExtractionCandidate.extraction_run_id == existing.extraction_run_id)
                        .order_by(ExtractionCandidate.candidate_id)
                    )
                )
                return existing.extraction_run_id, persisted_candidate_ids

            completed_at = session.scalar(select(text("clock_timestamp()")))
            assert isinstance(completed_at, datetime)
            block_ids = [block.block_id for block in prepared.prompt.blocks]
            lifecycle = FactLifecycleService(session)
            extraction_run_id = uuid7()
            lifecycle.persist_run(
                ExtractionRunSchemaV08(
                    extraction_run_id=extraction_run_id,
                    source_bundle_revision_id=prepared.source_bundle_revision_id,
                    target_scope=ExtractionTargetScope.OPPORTUNITY,
                    opportunity_id=prepared.opportunity_id,
                    opportunity_version=prepared.opportunity_version,
                    opportunity_unit_id=None,
                    opportunity_unit_version_id=None,
                    unit_segmentation_version=None,
                    task_spec_version=prepared.intent.task_spec_version,
                    extractor_kind=ExtractorKind.MODEL,
                    component_version="local-human-extraction-1.0.0",
                    producer_identity=producer_identity,
                    producer_response_id=response_id,
                    ordered_input_block_ids=block_ids,
                    input_block_set_hash=extraction_input_block_set_hash(block_ids),
                    evidence_binding_hash=extraction_evidence_binding_hash(
                        [
                            (block.block_id, block.evidence_binding_hash)
                            for block in prepared.prompt.blocks
                        ]
                    ),
                    started_at=prepared.intent.registered_at,
                    completed_at=completed_at,
                    status=(
                        ExtractionRunStatus.ABSTAINED
                        if all(fact.abstained for fact in envelope.facts)
                        else ExtractionRunStatus.SUCCEEDED
                    ),
                )
            )
            evidence_by_block = {
                block.block_id: block.evidence_ref_id for block in prepared.prompt.blocks
            }
            candidate_ids: list[UUID] = []
            for fact in envelope.facts:
                candidate_id = uuid7()
                lifecycle.record_candidate(
                    ExtractionCandidateSchemaV08(
                        candidate_id=candidate_id,
                        extraction_run_id=extraction_run_id,
                        target_scope=ExtractionTargetScope.OPPORTUNITY,
                        opportunity_id=prepared.opportunity_id,
                        opportunity_version=prepared.opportunity_version,
                        opportunity_unit_id=None,
                        opportunity_unit_version_id=None,
                        field_name=fact.field_name,
                        raw_value=fact.raw_value,
                        normalized_value_candidate=fact.normalized_value_candidate,
                        evidence_block_ids=list(fact.evidence_block_ids),
                        evidence_ref_ids=[
                            evidence_by_block[value] for value in fact.evidence_block_ids
                        ],
                        confidence=fact.confidence,
                        abstained=fact.abstained,
                        candidate_reason_code=fact.reason_code,
                        schema_version="0.8.0",
                        created_at=completed_at,
                    )
                )
                candidate_ids.append(candidate_id)
            return extraction_run_id, tuple(candidate_ids)

    def _fail(
        self,
        item_id: UUID,
        *,
        target: ItemStatus,
        error_code: str,
        model_call_id: UUID | None = None,
    ) -> ExtractionOutcome:
        references = {"model_call_id": model_call_id} if model_call_id is not None else None
        self._run_service.transition_item(
            item_id,
            expected=ItemStatus.EXTRACTING,
            target=target,
            error_code=error_code,
            references=references,
        )
        return ExtractionOutcome(
            item_id=item_id,
            status=target,
            model_call_id=model_call_id,
            extraction_run_id=None,
            candidate_ids=(),
            uncertainty_count=0,
        )


__all__ = [
    "EXTRACTION_SCHEMA_VERSION",
    "ExtractionConfigurationError",
    "ExtractionOutcome",
    "ExtractionPrompt",
    "ExtractionValidationError",
    "MinimizedExtractionBlock",
    "ModelExtractionEnvelope",
    "ModelFactCandidate",
    "ModelRuleCandidate",
    "P9BExtractionCoordinator",
    "build_extraction_messages",
    "parse_provider_envelope",
    "prepare_extraction_prompt",
    "validate_candidate_bindings",
]
