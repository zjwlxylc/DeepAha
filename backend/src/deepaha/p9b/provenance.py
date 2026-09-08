import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.opportunities.models import OpportunityVersion
from deepaha.p9b.hashing import canonical_bundle_hash, member_provenance_hash
from deepaha.p9b.models import (
    SourceBundle,
    SourceBundleMember,
    SourceBundleMemberRelation,
    SourceBundleRevision,
)
from deepaha.p9b.wma_provenance import (
    ACQUISITION_FIELDS,
    WmaBundleMemberSpec,
    materialize_wma_member,
)
from deepaha.sources.models import CaptureObservation


class BundleProvenanceError(ValueError):
    pass


@dataclass(frozen=True)
class BundleMemberSpec:
    document_id: UUID
    capture_observation_id: UUID
    acquisition_evaluation_id: UUID
    acquisition_run_id: UUID
    member_role: str
    precedence: int
    effective_from: datetime | None
    effective_to: datetime | None
    evidence_ref_id: UUID | None = None
    parse_attempt_id: UUID | None = None
    relation_type: str = "PRIMARY"
    related_member_index: int | None = None


def _instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.astimezone(UTC)
    fraction = f"{normalized.microsecond:06d}".rstrip("0")
    base = normalized.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{fraction}Z" if fraction else f"{base}Z"


def _member_payload(
    member: SourceBundleMember,
    *,
    relation_type: str,
    related_member_id: UUID | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_bundle_member_id": str(member.source_bundle_member_id),
        "source_bundle_revision_id": str(member.source_bundle_revision_id),
        "source_id": str(member.source_id),
        "endpoint_id": str(member.endpoint_id),
        "capture_observation_id": str(member.capture_observation_id),
        "acquisition_evaluation_id": str(member.acquisition_evaluation_id),
        "acquisition_validation_status": member.acquisition_validation_status,
        "acquisition_run_id": str(member.acquisition_run_id),
        "recipe_id": str(member.recipe_id),
        "recipe_version": member.recipe_version,
        "policy_version": member.policy_version,
        "fetch_strategy": member.fetch_strategy,
        "fetcher_name": member.fetcher_name,
        "fetcher_version": member.fetcher_version,
        "validator_name": member.validator_name,
        "validator_version": member.validator_version,
        "raw_artifact_id": str(member.raw_artifact_id),
        "raw_artifact_sha256": member.raw_artifact_sha256,
        "raw_artifact_size": member.raw_artifact_size,
        "storage_bucket": member.storage_bucket,
        "object_key": member.object_key,
        "document_id": str(member.document_id),
        "document_parse_key": member.document_parse_key,
        "parser_name": member.parser_name,
        "parser_version": member.parser_version,
        "parse_contract_version": member.parse_contract_version,
        "member_role": member.member_role,
        "relation_type": relation_type,
        "precedence": member.precedence,
        "related_member_id": str(related_member_id) if related_member_id else None,
        "effective_from": _instant(member.effective_from),
        "effective_to": _instant(member.effective_to),
    }
    if member.evidence_ref_id is not None:
        payload["evidence_ref_id"] = str(member.evidence_ref_id)
        payload["parse_attempt_id"] = str(member.parse_attempt_id)
    if member.provenance_kind == "DIRECT_WMA":
        for key in ACQUISITION_FIELDS:
            payload.pop(key)
        payload.update(
            provenance_kind="DIRECT_WMA",
            provenance_version="direct-wma-member/1",
            url_provenance="AGENT_DECLARED",
            wma_task_id=str(member.wma_task_id),
            wma_material_id=member.wma_material_id,
            wma_delivery_hash=member.wma_delivery_hash,
            wma_contract_hash=member.wma_contract_hash,
        )
    return payload


class BundleService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_revision(
        self,
        *,
        opportunity_id: UUID,
        opportunity_version: int,
        effective_as_of: datetime,
        members: Sequence[BundleMemberSpec | WmaBundleMemberSpec],
        source_bundle_id: UUID | None = None,
    ) -> SourceBundleRevision:
        if not members:
            raise BundleProvenanceError("SourceBundleRevision requires at least one member")
        if (
            self._session.get(
                OpportunityVersion,
                {"opportunity_id": opportunity_id, "version": opportunity_version},
            )
            is None
        ):
            raise BundleProvenanceError("OpportunityVersion composite identity does not exist")

        bundle = self._load_or_create_bundle(
            opportunity_id=opportunity_id,
            source_bundle_id=source_bundle_id,
            created_at=effective_as_of,
        )
        return self._create_revision(
            bundle=bundle,
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
            effective_as_of=effective_as_of,
            members=members,
        )

    def create_request_revision(
        self,
        *,
        request_key: str,
        request_payload_sha256: str,
        effective_as_of: datetime,
        members: Sequence[BundleMemberSpec | WmaBundleMemberSpec],
    ) -> SourceBundleRevision:
        if not members:
            raise BundleProvenanceError("SourceBundleRevision requires at least one member")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_key) is None:
            raise BundleProvenanceError("request key is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", request_payload_sha256) is None:
            raise BundleProvenanceError("request payload SHA-256 is invalid")
        existing = self._session.scalar(
            select(SourceBundle).where(SourceBundle.request_key == request_key)
        )
        if existing is not None:
            if existing.request_payload_sha256 != request_payload_sha256:
                raise BundleProvenanceError("request payload drift")
            raise BundleProvenanceError("request SourceBundle already exists")
        bundle = SourceBundle(
            source_bundle_id=uuid7(),
            opportunity_id=None,
            request_key=request_key,
            request_payload_sha256=request_payload_sha256,
            created_at=effective_as_of,
            retired_at=None,
        )
        self._session.add(bundle)
        self._session.flush()
        return self._create_revision(
            bundle=bundle,
            opportunity_id=None,
            opportunity_version=None,
            effective_as_of=effective_as_of,
            members=members,
        )

    def _create_revision(
        self,
        *,
        bundle: SourceBundle,
        opportunity_id: UUID | None,
        opportunity_version: int | None,
        effective_as_of: datetime,
        members: Sequence[BundleMemberSpec | WmaBundleMemberSpec],
    ) -> SourceBundleRevision:
        revision_number = (
            self._session.scalar(
                select(func.max(SourceBundleRevision.revision_number)).where(
                    SourceBundleRevision.source_bundle_id == bundle.source_bundle_id
                )
            )
            or 0
        ) + 1
        revision = SourceBundleRevision(
            source_bundle_revision_id=uuid7(),
            source_bundle_id=bundle.source_bundle_id,
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
            revision_number=revision_number,
            canonical_bundle_hash="0" * 64,
            relation_graph_version="p9b-member-relation-v0.8.0",
            precedence_graph_version="p9b-precedence-v0.8.0",
            effective_as_of=effective_as_of,
            status="DRAFT",
            created_at=effective_as_of,
            frozen_at=None,
        )
        self._session.add(revision)
        self._session.flush()

        rows = [
            self._materialize_member(revision.source_bundle_revision_id, spec) for spec in members
        ]
        for index, (row, spec) in enumerate(zip(rows, members, strict=True)):
            related_id = self._validate_relation(index=index, spec=spec, rows=rows)
            row.member_provenance_hash = member_provenance_hash(
                _member_payload(
                    row,
                    relation_type=spec.relation_type,
                    related_member_id=related_id,
                )
            )
        self._session.add_all(rows)
        self._session.flush()
        for index, (row, spec) in enumerate(zip(rows, members, strict=True)):
            related_id = self._validate_relation(index=index, spec=spec, rows=rows)
            if related_id is not None:
                self._session.add(
                    SourceBundleMemberRelation(
                        source_bundle_revision_id=revision.source_bundle_revision_id,
                        source_member_id=row.source_bundle_member_id,
                        target_member_id=related_id,
                        relation_type=spec.relation_type,
                        created_at=effective_as_of,
                    )
                )
        self._session.flush()
        return revision

    def freeze_revision(
        self,
        source_bundle_revision_id: UUID,
        *,
        frozen_at: datetime,
    ) -> SourceBundleRevision:
        revision = self._session.get(SourceBundleRevision, source_bundle_revision_id)
        if revision is None:
            raise BundleProvenanceError("SourceBundleRevision does not exist")
        if revision.status != "DRAFT":
            raise BundleProvenanceError("only a DRAFT SourceBundleRevision can freeze")
        members = tuple(
            self._session.scalars(
                select(SourceBundleMember)
                .where(SourceBundleMember.source_bundle_revision_id == source_bundle_revision_id)
                .order_by(SourceBundleMember.source_bundle_member_id)
            )
        )
        if not members:
            raise BundleProvenanceError("cannot freeze an empty SourceBundleRevision")
        relations = tuple(
            self._session.scalars(
                select(SourceBundleMemberRelation).where(
                    SourceBundleMemberRelation.source_bundle_revision_id
                    == source_bundle_revision_id
                )
            )
        )
        relation_by_source: dict[UUID, SourceBundleMemberRelation] = {}
        for edge in relations:
            if edge.source_member_id in relation_by_source:
                raise BundleProvenanceError("member has multiple relation edges")
            relation_by_source[edge.source_member_id] = edge

        for member in members:
            relation = relation_by_source.get(member.source_bundle_member_id)
            expected = member_provenance_hash(
                _member_payload(
                    member,
                    relation_type=relation.relation_type if relation else "PRIMARY",
                    related_member_id=relation.target_member_id if relation else None,
                )
            )
            if (
                member.provenance_kind != "DIRECT_WMA"
                and member.acquisition_validation_status != "VALID"
            ):
                raise BundleProvenanceError("only VALID members can freeze")
            if member.member_provenance_hash != expected:
                raise BundleProvenanceError("member provenance hash recomputation failed")

        revision.canonical_bundle_hash = canonical_bundle_hash(
            {
                "source_bundle_id": str(revision.source_bundle_id),
                "source_bundle_revision_id": str(revision.source_bundle_revision_id),
                "opportunity_id": (
                    str(revision.opportunity_id) if revision.opportunity_id is not None else None
                ),
                "opportunity_version": revision.opportunity_version,
                "revision_number": revision.revision_number,
                "effective_as_of": _instant(revision.effective_as_of),
                "relation_graph_version": revision.relation_graph_version,
                "precedence_graph_version": revision.precedence_graph_version,
                "member_provenance_hashes": [member.member_provenance_hash for member in members],
                "relations": sorted(
                    (
                        {
                            "source_member_id": str(relation.source_member_id),
                            "target_member_id": str(relation.target_member_id),
                            "relation_type": relation.relation_type,
                        }
                        for relation in relations
                    ),
                    key=lambda item: (
                        item["source_member_id"],
                        item["target_member_id"],
                        item["relation_type"],
                    ),
                ),
            }
        )
        revision.status = "FROZEN"
        revision.frozen_at = frozen_at
        self._session.flush()
        return revision

    def _load_or_create_bundle(
        self,
        *,
        opportunity_id: UUID,
        source_bundle_id: UUID | None,
        created_at: datetime,
    ) -> SourceBundle:
        if source_bundle_id is not None:
            bundle = self._session.get(SourceBundle, source_bundle_id)
            if bundle is None or bundle.opportunity_id != opportunity_id:
                raise BundleProvenanceError("SourceBundle opportunity binding mismatch")
            return bundle
        bundle = SourceBundle(
            source_bundle_id=uuid7(),
            opportunity_id=opportunity_id,
            request_key=None,
            request_payload_sha256=None,
            created_at=created_at,
            retired_at=None,
        )
        self._session.add(bundle)
        self._session.flush()
        return bundle

    def _materialize_member(
        self,
        revision_id: UUID,
        spec: BundleMemberSpec | WmaBundleMemberSpec,
    ) -> SourceBundleMember:
        if isinstance(spec, WmaBundleMemberSpec):
            return materialize_wma_member(self._session, revision_id, spec)
        document = self._session.get(Document, spec.document_id)
        observation = self._session.get(CaptureObservation, spec.capture_observation_id)
        evaluation = self._session.get(
            AcquisitionEvaluation,
            spec.acquisition_evaluation_id,
        )
        run = self._session.get(AcquisitionRun, spec.acquisition_run_id)
        if None in (document, observation, evaluation, run):
            raise BundleProvenanceError("member provenance identity does not exist")
        assert document is not None
        assert observation is not None
        assert evaluation is not None
        assert run is not None
        artifact = self._session.get(RawArtifact, document.artifact_id)
        if artifact is None:
            raise BundleProvenanceError("RawArtifact does not exist")
        if (spec.evidence_ref_id is None) != (spec.parse_attempt_id is None):
            raise BundleProvenanceError("EvidenceRef and ParseAttempt must be bound together")
        evidence_ref = (
            self._session.get(EvidenceRef, spec.evidence_ref_id)
            if spec.evidence_ref_id is not None
            else None
        )
        parse_attempt = (
            self._session.get(ParseAttempt, spec.parse_attempt_id)
            if spec.parse_attempt_id is not None
            else None
        )
        if spec.evidence_ref_id is not None and (evidence_ref is None or parse_attempt is None):
            raise BundleProvenanceError("EvidenceRef or ParseAttempt identity does not exist")
        exact_observation = (
            observation.artifact_id == artifact.artifact_id
            and observation.source_id == artifact.source_id
        )
        exact_evaluation = (
            evaluation.observation_id == observation.observation_id
            and evaluation.endpoint_id == observation.endpoint_id
            and evaluation.source_id == observation.source_id
            and evaluation.artifact_id == artifact.artifact_id
            and evaluation.validation_status == "VALID"
        )
        exact_run = (
            run.source_id == observation.source_id
            and run.endpoint_id == observation.endpoint_id
            and run.endpoint_policy_version == observation.policy_version
            and any(
                attempt.get("capture_observation_id") == str(observation.observation_id)
                and attempt.get("acquisition_evaluation_id")
                == str(evaluation.acquisition_evaluation_id)
                and attempt.get("raw_artifact_id") == str(artifact.artifact_id)
                for attempt in run.strategy_attempts
            )
        )
        if not exact_observation:
            raise BundleProvenanceError("CaptureObservation provenance binding mismatch")
        if not exact_evaluation:
            raise BundleProvenanceError("AcquisitionEvaluation must be exact and VALID")
        if not exact_run:
            raise BundleProvenanceError("AcquisitionRun must contain exact Observation lineage")
        if evidence_ref is not None:
            exact_evidence = (
                evidence_ref.document_id == document.document_id
                and evidence_ref.artifact_id == artifact.artifact_id
                and evidence_ref.locator_kind == "full_document"
                and evidence_ref.locator_value == "*"
                and evidence_ref.locator_schema_version == "0.1.0"
                and evidence_ref.quote_sha256 == artifact.content_sha256
            )
            exact_parse = (
                parse_attempt is not None
                and parse_attempt.document_id == document.document_id
                and parse_attempt.artifact_id == artifact.artifact_id
                and parse_attempt.parser_name == document.parser_name
                and parse_attempt.parser_version == document.parser_version
                and parse_attempt.parse_contract_version == document.parse_contract_version
                and parse_attempt.document_parse_key == document.document_parse_key
                and parse_attempt.outcome == "SUCCEEDED"
            )
            if not exact_evidence or not exact_parse:
                raise BundleProvenanceError("exact evidence or parse binding mismatch")
        return SourceBundleMember(
            provenance_kind="ACQUISITION",
            source_bundle_member_id=uuid7(),
            source_bundle_revision_id=revision_id,
            source_id=observation.source_id,
            endpoint_id=observation.endpoint_id,
            capture_observation_id=observation.observation_id,
            acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
            acquisition_validation_status=evaluation.validation_status,
            acquisition_run_id=run.acquisition_run_id,
            recipe_id=run.recipe_id,
            recipe_version=run.recipe_version,
            policy_version=observation.policy_version,
            fetch_strategy=evaluation.strategy_used,
            fetcher_name=observation.collector_name,
            fetcher_version=observation.collector_version,
            validator_name=evaluation.validator_name,
            validator_version=evaluation.validator_version,
            raw_artifact_id=artifact.artifact_id,
            raw_artifact_sha256=artifact.content_sha256,
            raw_artifact_size=artifact.byte_size,
            storage_bucket=artifact.storage_bucket,
            object_key=artifact.object_key,
            document_id=document.document_id,
            document_parse_key=document.document_parse_key,
            parser_name=document.parser_name,
            parser_version=document.parser_version,
            parse_contract_version=document.parse_contract_version,
            evidence_ref_id=spec.evidence_ref_id,
            parse_attempt_id=spec.parse_attempt_id,
            member_role=spec.member_role,
            precedence=spec.precedence,
            effective_from=spec.effective_from,
            effective_to=spec.effective_to,
            member_provenance_hash="0" * 64,
            created_at=observation.completed_at,
        )

    @staticmethod
    def _validate_relation(
        *,
        index: int,
        spec: BundleMemberSpec | WmaBundleMemberSpec,
        rows: list[SourceBundleMember],
    ) -> UUID | None:
        if spec.relation_type == "PRIMARY":
            if spec.related_member_index is not None:
                raise BundleProvenanceError("PRIMARY member cannot have a relation target")
            return None
        if spec.related_member_index is None:
            raise BundleProvenanceError("non-primary member requires a relation target")
        if spec.related_member_index == index or not 0 <= spec.related_member_index < len(rows):
            raise BundleProvenanceError("member relation target is invalid")
        return rows[spec.related_member_index].source_bundle_member_id


__all__ = ["BundleMemberSpec", "BundleProvenanceError", "BundleService"]
