import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated, Literal, Protocol
from uuid import uuid7

from pydantic import HttpUrl, StringConstraints
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    AcquisitionContract,
    DiscoveryKind,
    FetchResult,
    FetchStrategy,
    SourceRecipe,
    SourceUsageRole,
    ValidationResult,
    ValidationStatus,
)
from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.acquisition.recipes import recipe_allows_url
from deepaha.acquisition.validation import ContentValidator
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectMetadata, ObjectStore
from deepaha.artifacts.service import (
    ImportRawArtifactCommand,
    build_raw_object_key,
    import_raw_artifact,
)
from deepaha.contracts.common import EntityId
from deepaha.contracts.phase2 import SourceEndpointSchema
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.p9b.hashing import document_parse_key
from deepaha.p9b.models import SourceBundle, SourceBundleMember, SourceBundleRevision
from deepaha.p9b.provenance import BundleMemberSpec, BundleService
from deepaha.sources.collector import Clock, Sleeper, collect_http_attempts
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint
from deepaha.sources.transport import HostResolver, HttpTransport

COLLECTOR_NAME = "deepaha-http"
COLLECTOR_VERSION = "0.2.0"
PARSER_NAME = "deepaha-raw-snapshot"
PARSER_VERSION = "1.0.0"
PARSE_CONTRACT_VERSION = "p10b1-raw-snapshot-v1"

RequestKey = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
]


class OfficialEvidenceRequest(AcquisitionContract):
    request_key: RequestKey
    source_id: EntityId
    endpoint_id: EntityId
    recipe_id: EntityId
    requested_url: HttpUrl
    contract_version: Literal["1.0.0"]


class OfficialEvidencePolicyError(RuntimeError):
    code = "OFFICIAL_EVIDENCE_POLICY_REJECTED"

    def __init__(self) -> None:
        super().__init__(self.code)


class OfficialEvidencePayloadDrift(RuntimeError):
    code = "OFFICIAL_EVIDENCE_PAYLOAD_DRIFT"

    def __init__(self) -> None:
        super().__init__(self.code)


class OfficialEvidenceAcquisitionError(RuntimeError):
    code = "OFFICIAL_EVIDENCE_ACQUISITION_FAILED"

    def __init__(self, diagnostic_code: str) -> None:
        self.diagnostic_code = diagnostic_code
        super().__init__(f"{self.code}:{diagnostic_code}")


class OfficialEvidenceValidationError(RuntimeError):
    code = "OFFICIAL_EVIDENCE_VALIDATION_FAILED"

    def __init__(self, status: ValidationStatus) -> None:
        self.status = status
        super().__init__(f"{self.code}:{status.value}")


class OfficialEvidencePersistenceError(RuntimeError):
    code = "OFFICIAL_EVIDENCE_PERSISTENCE_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


class OfficialEvidenceCommitOutcomeUnknown(RuntimeError):
    code = "OFFICIAL_EVIDENCE_COMMIT_OUTCOME_UNKNOWN"

    def __init__(self) -> None:
        super().__init__(self.code)


class OfficialEvidenceResult(AcquisitionContract):
    request_key: RequestKey
    request_payload_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    source_bundle_id: EntityId
    source_bundle_revision_id: EntityId
    raw_artifact_id: EntityId
    document_id: EntityId
    evidence_ref_id: EntityId
    content_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    object_key: Annotated[str, StringConstraints(min_length=1)]
    retrieved_at: datetime
    replayed: bool
    contract_version: Literal["1.0.0"]


class CompensatingObjectStore(ObjectStore, Protocol):
    def stat_if_present(self, *, key: str) -> ObjectMetadata | None:
        raise NotImplementedError

    def delete_if_matches(self, *, key: str, sha256: str) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class AcquiredOfficialEvidence:
    started_at: datetime
    completed_at: datetime
    resolved_url: str
    redirect_chain: tuple[str, ...]
    http_status: int
    media_type: str | None
    response_etag: str | None
    response_last_modified: str | None
    body: bytes


def request_payload_sha256(request: OfficialEvidenceRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"request_key"})
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_official_evidence_policy(
    request: OfficialEvidenceRequest,
    source: Source,
    endpoint: SourceEndpoint,
    recipe: SourceRecipe,
) -> None:
    single_step = recipe.fetch_plan[0] if len(recipe.fetch_plan) == 1 else None
    accepted = (
        request.source_id == source.source_id == endpoint.source_id == recipe.source_id
        and request.endpoint_id == endpoint.endpoint_id == recipe.endpoint_id
        and request.recipe_id == recipe.recipe_id
        and source.tier == "OFFICIAL_PRIMARY"
        and source.active
        and endpoint.active
        and endpoint.browser_policy == "NEVER"
        and endpoint.robots_decision in {"ALLOWED", "NOT_APPLICABLE"}
        and endpoint.content_use_basis != "UNKNOWN"
        and recipe.active
        and recipe.usage_role is SourceUsageRole.PRIMARY_EVIDENCE
        and recipe.endpoint_policy_version == endpoint.policy_version
        and recipe.allowed_hosts == tuple(endpoint.allowed_hosts)
        and recipe.expected_media_types == tuple(endpoint.expected_media_types)
        and recipe.discovery.kind is DiscoveryKind.NONE
        and recipe.maximum_requests == 1
        and single_step is not None
        and single_step.strategy is FetchStrategy.STATIC_HTTP
        and not single_step.fallback_on
        and recipe_allows_url(recipe, str(request.requested_url))
    )
    if not accepted:
        raise OfficialEvidencePolicyError


class OfficialEvidenceTask:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        object_store: CompensatingObjectStore,
        recipes: tuple[SourceRecipe, ...],
        transport: HttpTransport,
        resolver: HostResolver,
        clock: Clock,
        sleeper: Sleeper,
    ) -> None:
        self._session_factory = session_factory
        self._object_store = object_store
        self._recipes = {recipe.recipe_id: recipe for recipe in recipes}
        if len(self._recipes) != len(recipes):
            raise ValueError("official evidence recipes contain duplicate identities")
        self._transport = transport
        self._resolver = resolver
        self._clock = clock
        self._sleeper = sleeper
        self._validator = ContentValidator()

    def run(self, request: OfficialEvidenceRequest) -> OfficialEvidenceResult:
        payload_sha256 = request_payload_sha256(request)
        with self._session_factory() as session:
            replay = self._load_replay(session, request.request_key, payload_sha256)
            if replay is not None:
                self._verify_object(replay)
                return replay
        recipe = self._recipes.get(request.recipe_id)
        if recipe is None:
            raise OfficialEvidencePolicyError
        digest: str | None = None
        object_key: str | None = None
        existed_before = True
        with self._session_factory() as session:
            transaction = session.begin()
            try:
                _advisory_lock(session, request.request_key, seed=0)
                replay = self._load_replay(session, request.request_key, payload_sha256)
                if replay is not None:
                    self._verify_object(replay)
                    try:
                        transaction.commit()
                    except Exception:
                        raise OfficialEvidenceCommitOutcomeUnknown from None
                    return replay
                source = session.get(Source, request.source_id)
                endpoint = session.get(SourceEndpoint, request.endpoint_id)
                if source is None or endpoint is None:
                    raise OfficialEvidencePolicyError
                validate_official_evidence_policy(request, source, endpoint, recipe)
                _advisory_lock(session, str(request.endpoint_id), seed=2)
                latest_capture_at = session.scalar(
                    select(CaptureObservation.completed_at)
                    .where(CaptureObservation.endpoint_id == request.endpoint_id)
                    .order_by(CaptureObservation.completed_at.desc())
                    .limit(1)
                )
                rate_limit_elapsed = latest_capture_at is None or self._clock.now() >= (
                    latest_capture_at + timedelta(seconds=endpoint.minimum_interval_seconds)
                )
                acquired, validation = self._acquire_and_validate(
                    request,
                    source,
                    endpoint,
                    recipe,
                    rate_limit_elapsed=rate_limit_elapsed,
                )
                digest = sha256(acquired.body).hexdigest()
                object_key = build_raw_object_key(digest)
                _advisory_lock(session, digest, seed=1)
                formal_artifact_exists = (
                    session.scalar(
                        select(RawArtifact.artifact_id).where(
                            RawArtifact.source_id == request.source_id,
                            RawArtifact.content_sha256 == digest,
                        )
                    )
                    is not None
                )
                existed_before = formal_artifact_exists or (
                    self._object_store.stat_if_present(key=object_key) is not None
                )
                result = self._persist(
                    session=session,
                    request=request,
                    payload_sha256=payload_sha256,
                    recipe=recipe,
                    acquired=acquired,
                    validation=validation,
                )
                try:
                    transaction.commit()
                except Exception:
                    raise OfficialEvidenceCommitOutcomeUnknown from None
                return result
            except OfficialEvidenceCommitOutcomeUnknown:
                raise
            except Exception as error:
                cleanup_failed = False
                if not existed_before and object_key is not None and digest is not None:
                    try:
                        self._object_store.delete_if_matches(key=object_key, sha256=digest)
                    except Exception:
                        cleanup_failed = True
                try:
                    transaction.rollback()
                except Exception:
                    raise OfficialEvidencePersistenceError from None
                if cleanup_failed:
                    raise OfficialEvidencePersistenceError from None
                if isinstance(
                    error,
                    (
                        OfficialEvidencePolicyError,
                        OfficialEvidencePayloadDrift,
                        OfficialEvidenceAcquisitionError,
                        OfficialEvidenceValidationError,
                        OfficialEvidencePersistenceError,
                    ),
                ):
                    raise
                raise OfficialEvidencePersistenceError from None

    def _acquire_and_validate(
        self,
        request: OfficialEvidenceRequest,
        source: Source,
        endpoint: SourceEndpoint,
        recipe: SourceRecipe,
        *,
        rate_limit_elapsed: bool,
    ) -> tuple[AcquiredOfficialEvidence, ValidationResult]:
        endpoint_contract = _endpoint_contract(endpoint).model_copy(
            update={
                "url": request.requested_url,
                "max_attempts": 1,
                "timeout_seconds": min(
                    endpoint.timeout_seconds,
                    recipe.maximum_elapsed_seconds,
                ),
            }
        )
        decisions = tuple(
            collect_http_attempts(
                endpoint=endpoint_contract,
                source_active=source.active,
                rate_limit_elapsed=rate_limit_elapsed,
                previous_artifact_id=None,
                conditional_etag=None,
                conditional_last_modified=None,
                transport=self._transport,
                resolver=self._resolver,
                clock=self._clock,
                sleeper=self._sleeper,
                max_bytes=recipe.expectations.maximum_bytes,
                capture_unexpected_content=False,
                max_redirects=0,
            )
        )
        if not decisions:
            raise OfficialEvidenceAcquisitionError("NO_ATTEMPT")
        decision = decisions[-1]
        if (
            decision.outcome != "SUCCEEDED"
            or decision.body is None
            or decision.resolved_url is None
            or decision.http_status is None
        ):
            raise OfficialEvidenceAcquisitionError(decision.error_code or "NO_SUCCESSFUL_RESPONSE")
        digest = sha256(decision.body).hexdigest()
        fetch_result = FetchResult.model_validate(
            {
                "request_id": uuid7(),
                "source_id": request.source_id,
                "endpoint_id": request.endpoint_id,
                "observation_id": None,
                "artifact_id": None,
                "requested_url": request.requested_url,
                "final_url": decision.resolved_url,
                "redirect_chain": decision.redirect_chain,
                "strategy": "STATIC_HTTP",
                "fetched_at": decision.completed_at,
                "outcome": "SUCCEEDED",
                "http_status": decision.http_status,
                "media_type": decision.media_type,
                "safe_headers": {},
                "body": decision.body,
                "body_object_key": None,
                "content_sha256": digest,
                "byte_size": len(decision.body),
                "fetcher_name": COLLECTOR_NAME,
                "fetcher_version": COLLECTOR_VERSION,
                "error_code": None,
                "contract_version": "1.0.0",
            }
        )
        validation = self._validator.evaluate(fetch_result, recipe.expectations)
        if validation.status is not ValidationStatus.VALID:
            raise OfficialEvidenceValidationError(validation.status)
        return (
            AcquiredOfficialEvidence(
                started_at=decision.started_at,
                completed_at=decision.completed_at,
                resolved_url=decision.resolved_url,
                redirect_chain=decision.redirect_chain,
                http_status=decision.http_status,
                media_type=decision.media_type,
                response_etag=decision.response_etag,
                response_last_modified=decision.response_last_modified,
                body=decision.body,
            ),
            validation,
        )

    def _persist(
        self,
        *,
        session: Session,
        request: OfficialEvidenceRequest,
        payload_sha256: str,
        recipe: SourceRecipe,
        acquired: AcquiredOfficialEvidence,
        validation: ValidationResult,
    ) -> OfficialEvidenceResult:
        imported = import_raw_artifact(
            session=session,
            object_store=self._object_store,
            reuse_content_identity=True,
            command=ImportRawArtifactCommand(
                source_id=request.source_id,
                requested_url=str(request.requested_url),
                resolved_url=acquired.resolved_url,
                retrieved_at=acquired.completed_at,
                http_status=acquired.http_status,
                media_type=acquired.media_type,
                content=acquired.body,
                collector_version=COLLECTOR_VERSION,
                metadata_schema_version="0.2.0",
            ),
        )
        artifact = imported.artifact
        observation_id = uuid7()
        collection_run_id = uuid7()
        evaluation_id = uuid7()
        run_id = uuid7()
        observation = CaptureObservation(
            observation_id=observation_id,
            collection_run_id=collection_run_id,
            attempt_number=1,
            endpoint_id=request.endpoint_id,
            source_id=request.source_id,
            requested_url=str(request.requested_url),
            resolved_url=acquired.resolved_url,
            started_at=acquired.started_at,
            completed_at=acquired.completed_at,
            outcome="SUCCEEDED",
            http_status=acquired.http_status,
            response_etag=acquired.response_etag,
            response_last_modified=acquired.response_last_modified,
            artifact_id=artifact.artifact_id,
            error_code=None,
            collector_name=COLLECTOR_NAME,
            collector_version=COLLECTOR_VERSION,
            policy_version=recipe.endpoint_policy_version,
        )
        evaluation = AcquisitionEvaluation(
            acquisition_evaluation_id=evaluation_id,
            observation_id=observation_id,
            endpoint_id=request.endpoint_id,
            source_id=request.source_id,
            artifact_id=artifact.artifact_id,
            strategy_used="STATIC_HTTP",
            validation_status="VALID",
            challenge_type=None,
            redirect_chain=list(acquired.redirect_chain),
            discovered_count=None,
            manual_intervention=False,
            diagnostic_codes=list(validation.diagnostic_codes),
            validator_name=validation.validator_name,
            validator_version=validation.validator_version,
            metrics_schema_version=validation.metrics_schema_version,
            validation_metrics=dict(validation.metrics),
            evaluated_at=acquired.completed_at,
            contract_version="1.0.0",
        )
        run = AcquisitionRun(
            acquisition_run_id=run_id,
            recipe_id=recipe.recipe_id,
            source_id=request.source_id,
            endpoint_id=request.endpoint_id,
            endpoint_policy_version=recipe.endpoint_policy_version,
            recipe_version=recipe.recipe_version,
            started_at=acquired.started_at,
            completed_at=acquired.completed_at,
            terminal_code="COMPLETE",
            request_count=1,
            strategy_attempts=[
                {
                    "strategy": "STATIC_HTTP",
                    "outcome": "VALID",
                    "capture_observation_id": str(observation_id),
                    "acquisition_evaluation_id": str(evaluation_id),
                    "raw_artifact_id": str(artifact.artifact_id),
                }
            ],
            discovered_count=0,
            validated_count=1,
            parsed_count=1,
            attachment_count=0,
            evidence_count=1,
            zero_discovery_flag=False,
            selector_drift_flag=False,
            manual_intervention=False,
            stable_stop_reason=None,
            contract_version="1.0.0",
        )
        session.add(observation)
        session.flush()
        session.add_all([evaluation, run])
        session.flush()

        parse_key = document_parse_key(
            artifact_id=artifact.artifact_id,
            artifact_sha256=artifact.content_sha256,
            parser_name=PARSER_NAME,
            parser_version=PARSER_VERSION,
            parse_contract_version=PARSE_CONTRACT_VERSION,
        )
        document = session.scalar(
            select(Document).where(
                Document.artifact_id == artifact.artifact_id,
                Document.parser_name == PARSER_NAME,
                Document.parser_version == PARSER_VERSION,
                Document.parse_contract_version == PARSE_CONTRACT_VERSION,
            )
        )
        if document is None:
            document = Document(
                document_id=uuid7(),
                artifact_id=artifact.artifact_id,
                title=None,
                published_at=None,
                language="und",
                extracted_text_uri=None,
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
                parse_contract_version=PARSE_CONTRACT_VERSION,
                document_parse_key=parse_key,
                parse_confidence=None,
                created_at=acquired.completed_at,
            )
            session.add(document)
            session.flush()
        elif document.document_parse_key != parse_key:
            raise OfficialEvidencePersistenceError
        document_id = document.document_id

        parse_attempt = session.scalar(
            select(ParseAttempt).where(
                ParseAttempt.artifact_id == artifact.artifact_id,
                ParseAttempt.parser_name == PARSER_NAME,
                ParseAttempt.parser_version == PARSER_VERSION,
                ParseAttempt.parse_contract_version == PARSE_CONTRACT_VERSION,
            )
        )
        if parse_attempt is None:
            parse_attempt = ParseAttempt(
                parse_attempt_id=uuid7(),
                artifact_id=artifact.artifact_id,
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
                parse_contract_version=PARSE_CONTRACT_VERSION,
                document_parse_key=parse_key,
                started_at=acquired.completed_at,
                completed_at=acquired.completed_at,
                outcome="SUCCEEDED",
                document_id=document_id,
                error_code=None,
                input_media_type=acquired.media_type,
            )
            session.add(parse_attempt)
        elif (
            parse_attempt.document_id != document_id
            or parse_attempt.document_parse_key != parse_key
            or parse_attempt.outcome != "SUCCEEDED"
        ):
            raise OfficialEvidencePersistenceError

        evidence_ref = session.scalar(
            select(EvidenceRef).where(
                EvidenceRef.document_id == document_id,
                EvidenceRef.artifact_id == artifact.artifact_id,
                EvidenceRef.locator_kind == "full_document",
                EvidenceRef.locator_value == "*",
                EvidenceRef.locator_schema_version == "0.1.0",
                EvidenceRef.quote_sha256 == artifact.content_sha256,
            )
        )
        if evidence_ref is None:
            evidence_ref = EvidenceRef(
                evidence_ref_id=uuid7(),
                document_id=document_id,
                artifact_id=artifact.artifact_id,
                locator_kind="full_document",
                locator_value="*",
                locator_schema_version="0.1.0",
                locator_payload=None,
                quote_sha256=artifact.content_sha256,
            )
            session.add(evidence_ref)
        session.flush()
        evidence_ref_id = evidence_ref.evidence_ref_id
        bundle_service = BundleService(session)
        revision = bundle_service.create_request_revision(
            request_key=request.request_key,
            request_payload_sha256=payload_sha256,
            effective_as_of=acquired.completed_at,
            members=[
                BundleMemberSpec(
                    document_id=document_id,
                    capture_observation_id=observation_id,
                    acquisition_evaluation_id=evaluation_id,
                    acquisition_run_id=run_id,
                    evidence_ref_id=evidence_ref_id,
                    parse_attempt_id=parse_attempt.parse_attempt_id,
                    member_role="PRIMARY_NOTICE",
                    precedence=1000,
                    effective_from=acquired.completed_at,
                    effective_to=None,
                )
            ],
        )
        revision = bundle_service.freeze_revision(
            revision.source_bundle_revision_id,
            frozen_at=acquired.completed_at,
        )
        return OfficialEvidenceResult(
            request_key=request.request_key,
            request_payload_sha256=payload_sha256,
            source_bundle_id=revision.source_bundle_id,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            raw_artifact_id=artifact.artifact_id,
            document_id=document_id,
            evidence_ref_id=evidence_ref_id,
            content_sha256=artifact.content_sha256,
            object_key=artifact.object_key,
            retrieved_at=acquired.completed_at,
            replayed=False,
            contract_version="1.0.0",
        )

    def _load_replay(
        self,
        session: Session,
        request_key: str,
        payload_sha256: str,
    ) -> OfficialEvidenceResult | None:
        bundle = session.scalar(select(SourceBundle).where(SourceBundle.request_key == request_key))
        if bundle is None:
            return None
        if bundle.request_payload_sha256 != payload_sha256:
            raise OfficialEvidencePayloadDrift
        revision = session.scalar(
            select(SourceBundleRevision)
            .where(
                SourceBundleRevision.source_bundle_id == bundle.source_bundle_id,
                SourceBundleRevision.status == "FROZEN",
            )
            .order_by(SourceBundleRevision.revision_number.desc())
            .limit(1)
        )
        if revision is None:
            raise OfficialEvidencePersistenceError
        members = session.scalars(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == revision.source_bundle_revision_id
            )
        ).all()
        if len(members) != 1:
            raise OfficialEvidencePersistenceError
        member = members[0]
        artifact = session.get(RawArtifact, member.raw_artifact_id)
        observation = session.get(CaptureObservation, member.capture_observation_id)
        evidence_ref = session.get(EvidenceRef, member.evidence_ref_id)
        parse_attempt = session.get(ParseAttempt, member.parse_attempt_id)
        if (
            member.member_role != "PRIMARY_NOTICE"
            or artifact is None
            or observation is None
            or evidence_ref is None
            or parse_attempt is None
            or evidence_ref.document_id != member.document_id
            or evidence_ref.artifact_id != artifact.artifact_id
            or evidence_ref.locator_kind != "full_document"
            or evidence_ref.locator_value != "*"
            or evidence_ref.locator_schema_version != "0.1.0"
            or evidence_ref.quote_sha256 != artifact.content_sha256
            or parse_attempt.document_id != member.document_id
            or parse_attempt.artifact_id != artifact.artifact_id
            or parse_attempt.document_parse_key != member.document_parse_key
            or parse_attempt.parser_name != member.parser_name
            or parse_attempt.parser_version != member.parser_version
            or parse_attempt.parse_contract_version != member.parse_contract_version
            or parse_attempt.outcome != "SUCCEEDED"
        ):
            raise OfficialEvidencePersistenceError
        return OfficialEvidenceResult(
            request_key=request_key,
            request_payload_sha256=payload_sha256,
            source_bundle_id=bundle.source_bundle_id,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            raw_artifact_id=artifact.artifact_id,
            document_id=member.document_id,
            evidence_ref_id=evidence_ref.evidence_ref_id,
            content_sha256=artifact.content_sha256,
            object_key=artifact.object_key,
            retrieved_at=observation.completed_at,
            replayed=True,
            contract_version="1.0.0",
        )

    def _verify_object(self, result: OfficialEvidenceResult) -> None:
        try:
            metadata = self._object_store.stat(key=result.object_key)
            content = self._object_store.get_bytes(key=result.object_key)
        except Exception:
            raise OfficialEvidencePersistenceError from None
        if (
            metadata.key != result.object_key
            or metadata.sha256 != result.content_sha256
            or metadata.byte_size != len(content)
            or sha256(content).hexdigest() != result.content_sha256
        ):
            raise OfficialEvidencePersistenceError


def _endpoint_contract(row: SourceEndpoint) -> SourceEndpointSchema:
    return SourceEndpointSchema.model_validate(
        {column.name: getattr(row, column.name) for column in SourceEndpoint.__table__.columns}
    )


def _advisory_lock(session: Session, value: str, *, seed: int) -> None:
    session.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:value, :seed))"),
        {"value": value, "seed": seed},
    )


__all__ = [
    "CompensatingObjectStore",
    "OfficialEvidenceAcquisitionError",
    "OfficialEvidenceCommitOutcomeUnknown",
    "OfficialEvidencePayloadDrift",
    "OfficialEvidencePersistenceError",
    "OfficialEvidencePolicyError",
    "OfficialEvidenceRequest",
    "OfficialEvidenceResult",
    "OfficialEvidenceTask",
    "OfficialEvidenceValidationError",
    "request_payload_sha256",
    "validate_official_evidence_policy",
]
