from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    FactVerificationDecisionSchemaV08,
)
from deepaha.documents.models import DocumentBlock
from deepaha.p9b.hashing import (
    extraction_evidence_binding_hash,
    fact_dependency_fingerprint,
)
from deepaha.p9b.hashing import (
    extraction_input_block_set_hash as _input_hash,
)
from deepaha.p9b.models import (
    ExtractionCandidate,
    ExtractionCandidateEvidence,
    ExtractionRun,
    ExtractionRunInputBlock,
    FactVerificationDecisionModel,
    SourceBundleMember,
    SourceBundleRevision,
    VerifiedFact,
    VerifiedFactEvidence,
    VerifiedFactSetDependency,
    VerifiedFactSetTransition,
    VersionedVerifiedFactSet,
)


class FactLifecycleError(ValueError):
    """A fail-closed P9-B fact lifecycle boundary was violated."""


def extraction_input_block_set_hash(block_ids: list[UUID] | tuple[UUID, ...]) -> str:
    return _input_hash(block_ids)


def ensure_independent_verification(
    *,
    producer_identity: str,
    producer_response_id: str | None,
    verifier_identity: str,
    verifier_response_id: str | None,
) -> None:
    if producer_identity == verifier_identity:
        raise FactLifecycleError("verification must use an independent verifier identity")
    if (
        producer_response_id is not None
        and verifier_response_id is not None
        and producer_response_id == verifier_response_id
    ):
        raise FactLifecycleError("verification must not reuse the producer response")


class FactLifecycleService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_run(self, contract: ExtractionRunSchemaV08) -> ExtractionRun:
        revision = self._session.get(SourceBundleRevision, contract.source_bundle_revision_id)
        if revision is None or revision.status != "FROZEN":
            raise FactLifecycleError("extraction requires a FROZEN SourceBundleRevision")
        if (
            revision.opportunity_id != contract.opportunity_id
            or revision.opportunity_version != contract.opportunity_version
        ):
            raise FactLifecycleError("extraction target does not match bundle revision")

        blocks = self._ordered_blocks(contract.ordered_input_block_ids)
        member_documents = set(
            self._session.scalars(
                select(SourceBundleMember.document_id).where(
                    SourceBundleMember.source_bundle_revision_id
                    == contract.source_bundle_revision_id
                )
            )
        )
        if any(block.document_id not in member_documents for block in blocks):
            raise FactLifecycleError("input block is outside the SourceBundleRevision")
        expected_evidence_hash = extraction_evidence_binding_hash(
            [(block.block_id, block.evidence_binding_hash) for block in blocks]
        )
        if contract.evidence_binding_hash != expected_evidence_hash:
            raise FactLifecycleError("extraction evidence binding hash mismatch")

        row = ExtractionRun(
            extraction_run_id=contract.extraction_run_id,
            source_bundle_revision_id=contract.source_bundle_revision_id,
            target_scope=contract.target_scope.value,
            opportunity_id=contract.opportunity_id,
            opportunity_version=contract.opportunity_version,
            opportunity_unit_id=contract.opportunity_unit_id,
            opportunity_unit_version_id=contract.opportunity_unit_version_id,
            unit_segmentation_version=contract.unit_segmentation_version,
            task_spec_version=contract.task_spec_version,
            extractor_kind=contract.extractor_kind.value,
            component_version=contract.component_version,
            producer_identity=contract.producer_identity,
            producer_response_id=contract.producer_response_id,
            ordered_input_block_ids=[
                str(block_id) for block_id in contract.ordered_input_block_ids
            ],
            input_block_set_hash=contract.input_block_set_hash,
            evidence_binding_hash=contract.evidence_binding_hash,
            started_at=contract.started_at,
            completed_at=contract.completed_at,
            status=contract.status.value,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                ExtractionRunInputBlock(
                    extraction_run_id=row.extraction_run_id,
                    input_ordinal=index,
                    block_id=block.block_id,
                    evidence_ref_id=block.evidence_ref_id,
                    document_id=block.document_id,
                )
                for index, block in enumerate(blocks, start=1)
            ]
        )
        self._session.flush()
        return row

    def record_candidate(self, contract: ExtractionCandidateSchemaV08) -> ExtractionCandidate:
        run = self._session.get(ExtractionRun, contract.extraction_run_id)
        if run is None:
            raise FactLifecycleError("ExtractionRun does not exist")
        self._require_same_target(run, contract)
        input_rows = {
            row.block_id: row
            for row in self._session.scalars(
                select(ExtractionRunInputBlock).where(
                    ExtractionRunInputBlock.extraction_run_id == run.extraction_run_id
                )
            )
        }
        pairs = list(zip(contract.evidence_block_ids, contract.evidence_ref_ids, strict=True))
        for block_id, evidence_ref_id in pairs:
            input_row = input_rows.get(block_id)
            if input_row is None or input_row.evidence_ref_id != evidence_ref_id:
                raise FactLifecycleError("candidate evidence is not an exact run input binding")

        row = ExtractionCandidate(
            candidate_id=contract.candidate_id,
            extraction_run_id=contract.extraction_run_id,
            target_scope=contract.target_scope.value,
            opportunity_id=contract.opportunity_id,
            opportunity_version=contract.opportunity_version,
            opportunity_unit_id=contract.opportunity_unit_id,
            opportunity_unit_version_id=contract.opportunity_unit_version_id,
            field_name=contract.field_name,
            raw_value=contract.raw_value,
            normalized_value_candidate=contract.normalized_value_candidate,
            confidence=contract.confidence,
            abstained=contract.abstained,
            candidate_reason_code=contract.candidate_reason_code,
            schema_version=contract.schema_version,
            created_at=contract.created_at,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                ExtractionCandidateEvidence(
                    candidate_id=row.candidate_id,
                    extraction_run_id=row.extraction_run_id,
                    block_id=block_id,
                    evidence_ref_id=evidence_ref_id,
                    document_id=input_rows[block_id].document_id,
                )
                for block_id, evidence_ref_id in pairs
            ]
        )
        self._session.flush()
        return row

    def verify_candidate(
        self, contract: FactVerificationDecisionSchemaV08
    ) -> FactVerificationDecisionModel:
        candidate = self._session.get(ExtractionCandidate, contract.candidate_id)
        if candidate is None:
            raise FactLifecycleError("ExtractionCandidate does not exist")
        run = self._session.get(ExtractionRun, candidate.extraction_run_id)
        assert run is not None
        ensure_independent_verification(
            producer_identity=run.producer_identity,
            producer_response_id=run.producer_response_id,
            verifier_identity=contract.verifier_identity,
            verifier_response_id=contract.verifier_response_id,
        )
        if contract.decision == "APPROVE" and candidate.abstained:
            raise FactLifecycleError("abstained candidate cannot be APPROVED as a known fact")
        if contract.decision == "UNKNOWN" and not candidate.abstained:
            raise FactLifecycleError("UNKNOWN decision requires an abstained candidate")

        row = FactVerificationDecisionModel(
            decision_id=contract.decision_id,
            candidate_id=contract.candidate_id,
            decision=contract.decision.value,
            verification_method=contract.verification_method.value,
            verifier_identity=contract.verifier_identity,
            verifier_response_id=contract.verifier_response_id,
            reason_code=contract.reason_code,
            evidence_support_result=contract.evidence_support_result.value,
            precedence_check_result=contract.precedence_check_result.value,
            decided_at=contract.decided_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def promote(
        self,
        *,
        decision_ids: Sequence[UUID],
        verified_fact_set_id: UUID,
        reference_dataset_versions: dict[str, str],
        created_at: datetime,
        supersedes_id: UUID | None = None,
        actor_identity: str = "component:p9b-fact-promotion/0.8.0",
    ) -> VersionedVerifiedFactSet:
        if not decision_ids or len(decision_ids) != len(set(decision_ids)):
            raise FactLifecycleError("promotion requires unique verification decisions")
        decisions = self._ordered_decisions(decision_ids)
        candidates = [self._required_candidate(decision.candidate_id) for decision in decisions]
        runs = [self._required_run(candidate.extraction_run_id) for candidate in candidates]
        self._require_common_promotion_target(runs, candidates, decisions)
        first_run = runs[0]
        revision = self._session.get(SourceBundleRevision, first_run.source_bundle_revision_id)
        if revision is None or revision.status != "FROZEN":
            raise FactLifecycleError("promotion requires a FROZEN SourceBundleRevision")
        if not reference_dataset_versions or any(
            not key.strip() or not value.strip()
            for key, value in reference_dataset_versions.items()
        ):
            raise FactLifecycleError("reference dataset versions must be explicit")

        active = self._active_fact_set(first_run)
        if supersedes_id is None and active is not None:
            raise FactLifecycleError("active fact set exists; explicit supersedes_id is required")
        if supersedes_id is not None and (
            active is None or active.verified_fact_set_id != supersedes_id
        ):
            raise FactLifecycleError("supersedes_id must name the current active fact set")
        next_version = 1 if active is None else active.version + 1

        if active is not None:
            self._session.add(
                VerifiedFactSetTransition(
                    transition_id=uuid7(),
                    verified_fact_set_id=active.verified_fact_set_id,
                    from_status="ACTIVE",
                    to_status="SUPERSEDED",
                    successor_fact_set_id=verified_fact_set_id,
                    dependency_id=None,
                    expected_dependency_fingerprint=None,
                    observed_dependency_fingerprint=None,
                    reason_code="SUPERSEDED_BY_VERIFIED_FACT_SET",
                    actor_identity=actor_identity,
                    created_at=created_at,
                )
            )
            self._session.flush()
            active.status = "SUPERSEDED"
            active.updated_at = created_at
            self._session.flush()

        fact_set = VersionedVerifiedFactSet(
            verified_fact_set_id=verified_fact_set_id,
            target_scope=first_run.target_scope,
            opportunity_id=first_run.opportunity_id,
            opportunity_version=first_run.opportunity_version,
            opportunity_unit_id=first_run.opportunity_unit_id,
            opportunity_unit_version_id=first_run.opportunity_unit_version_id,
            source_bundle_revision_id=first_run.source_bundle_revision_id,
            version=next_version,
            relation_graph_version=revision.relation_graph_version,
            precedence_graph_version=revision.precedence_graph_version,
            reference_dataset_versions=dict(sorted(reference_dataset_versions.items())),
            fact_schema_version="0.8.0",
            status="ACTIVE",
            supersedes_id=supersedes_id,
            created_at=created_at,
            updated_at=created_at,
        )
        self._session.add(fact_set)
        self._session.flush()

        all_evidence: list[ExtractionCandidateEvidence] = []
        for decision, candidate in zip(decisions, candidates, strict=True):
            evidence = list(
                self._session.scalars(
                    select(ExtractionCandidateEvidence).where(
                        ExtractionCandidateEvidence.candidate_id == candidate.candidate_id
                    )
                )
            )
            if not evidence:
                raise FactLifecycleError("candidate has no persisted evidence")
            all_evidence.extend(evidence)
            fingerprint = fact_dependency_fingerprint(
                {
                    "candidate_id": str(candidate.candidate_id),
                    "decision_id": str(decision.decision_id),
                    "evidence": [
                        {
                            "block_id": str(item.block_id),
                            "evidence_ref_id": str(item.evidence_ref_id),
                        }
                        for item in sorted(evidence, key=lambda item: str(item.block_id))
                    ],
                }
            )
            fact = VerifiedFact(
                verified_fact_id=uuid7(),
                verified_fact_set_id=fact_set.verified_fact_set_id,
                candidate_id=candidate.candidate_id,
                field_name=candidate.field_name,
                fact_state="UNKNOWN" if candidate.abstained else "KNOWN",
                normalized_value=candidate.normalized_value_candidate,
                raw_value=candidate.raw_value,
                verification_decision_id=decision.decision_id,
                dependency_fingerprint=fingerprint,
                created_at=created_at,
            )
            self._session.add(fact)
            self._session.flush()
            self._session.add_all(
                [
                    VerifiedFactEvidence(
                        verified_fact_id=fact.verified_fact_id,
                        verified_fact_set_id=fact_set.verified_fact_set_id,
                        candidate_id=candidate.candidate_id,
                        block_id=item.block_id,
                        evidence_ref_id=item.evidence_ref_id,
                    )
                    for item in evidence
                ]
            )

        self._session.add(
            VerifiedFactSetDependency(
                dependency_id=uuid7(),
                verified_fact_set_id=fact_set.verified_fact_set_id,
                dependency_type="SOURCE_BUNDLE_REVISION",
                source_bundle_revision_id=revision.source_bundle_revision_id,
                block_id=None,
                dependency_fingerprint=revision.canonical_bundle_hash,
                created_at=created_at,
            )
        )
        block_ids = sorted({item.block_id for item in all_evidence}, key=str)
        blocks_by_id = {block.block_id: block for block in self._ordered_blocks(block_ids)}
        self._session.add_all(
            [
                VerifiedFactSetDependency(
                    dependency_id=uuid7(),
                    verified_fact_set_id=fact_set.verified_fact_set_id,
                    dependency_type="DOCUMENT_BLOCK",
                    source_bundle_revision_id=None,
                    block_id=block_id,
                    dependency_fingerprint=blocks_by_id[block_id].evidence_binding_hash,
                    created_at=created_at,
                )
                for block_id in block_ids
            ]
        )
        self._session.flush()
        return fact_set

    def invalidate_dependency(
        self,
        *,
        verified_fact_set_id: UUID,
        dependency_id: UUID,
        observed_dependency_fingerprint: str,
        reason_code: str,
        actor_identity: str,
        created_at: datetime,
    ) -> VersionedVerifiedFactSet:
        fact_set = self._session.get(VersionedVerifiedFactSet, verified_fact_set_id)
        dependency = self._session.get(VerifiedFactSetDependency, dependency_id)
        if fact_set is None or fact_set.status != "ACTIVE":
            raise FactLifecycleError("only an ACTIVE fact set can become STALE")
        if dependency is None or dependency.verified_fact_set_id != verified_fact_set_id:
            raise FactLifecycleError("dependency does not belong to fact set")
        if observed_dependency_fingerprint == dependency.dependency_fingerprint:
            raise FactLifecycleError("unchanged dependency cannot invalidate a fact set")
        self._session.add(
            VerifiedFactSetTransition(
                transition_id=uuid7(),
                verified_fact_set_id=fact_set.verified_fact_set_id,
                from_status="ACTIVE",
                to_status="STALE",
                successor_fact_set_id=None,
                dependency_id=dependency.dependency_id,
                expected_dependency_fingerprint=dependency.dependency_fingerprint,
                observed_dependency_fingerprint=observed_dependency_fingerprint,
                reason_code=reason_code,
                actor_identity=actor_identity,
                created_at=created_at,
            )
        )
        self._session.flush()
        fact_set.status = "STALE"
        fact_set.updated_at = created_at
        self._session.flush()
        return fact_set

    def _ordered_blocks(self, block_ids: Sequence[UUID]) -> list[DocumentBlock]:
        rows = {
            block.block_id: block
            for block in self._session.scalars(
                select(DocumentBlock).where(DocumentBlock.block_id.in_(block_ids))
            )
        }
        if len(rows) != len(block_ids):
            raise FactLifecycleError("one or more DocumentBlocks do not exist")
        return [rows[block_id] for block_id in block_ids]

    def _ordered_decisions(
        self, decision_ids: Sequence[UUID]
    ) -> list[FactVerificationDecisionModel]:
        rows = {
            row.decision_id: row
            for row in self._session.scalars(
                select(FactVerificationDecisionModel).where(
                    FactVerificationDecisionModel.decision_id.in_(decision_ids)
                )
            )
        }
        if len(rows) != len(decision_ids):
            raise FactLifecycleError("one or more verification decisions do not exist")
        return [rows[decision_id] for decision_id in decision_ids]

    def _active_fact_set(self, run: ExtractionRun) -> VersionedVerifiedFactSet | None:
        statement = select(VersionedVerifiedFactSet).where(
            VersionedVerifiedFactSet.status == "ACTIVE",
            VersionedVerifiedFactSet.target_scope == run.target_scope,
        )
        if run.target_scope == "UNIT":
            statement = statement.where(
                VersionedVerifiedFactSet.opportunity_unit_id == run.opportunity_unit_id,
                VersionedVerifiedFactSet.opportunity_unit_version_id
                == run.opportunity_unit_version_id,
            )
        else:
            statement = statement.where(
                VersionedVerifiedFactSet.opportunity_id == run.opportunity_id,
                VersionedVerifiedFactSet.opportunity_version == run.opportunity_version,
            )
        return self._session.scalar(statement.with_for_update())

    @staticmethod
    def _require_same_target(run: ExtractionRun, contract: ExtractionCandidateSchemaV08) -> None:
        observed = (
            contract.target_scope.value,
            contract.opportunity_id,
            contract.opportunity_version,
            contract.opportunity_unit_id,
            contract.opportunity_unit_version_id,
        )
        expected = (
            run.target_scope,
            run.opportunity_id,
            run.opportunity_version,
            run.opportunity_unit_id,
            run.opportunity_unit_version_id,
        )
        if observed != expected:
            raise FactLifecycleError("candidate target does not match ExtractionRun")

    def _required_candidate(self, candidate_id: UUID) -> ExtractionCandidate:
        candidate = self._session.get(ExtractionCandidate, candidate_id)
        if candidate is None:
            raise FactLifecycleError("ExtractionCandidate does not exist")
        return candidate

    def _required_run(self, run_id: UUID) -> ExtractionRun:
        run = self._session.get(ExtractionRun, run_id)
        if run is None:
            raise FactLifecycleError("ExtractionRun does not exist")
        return run

    @staticmethod
    def _require_common_promotion_target(
        runs: Sequence[ExtractionRun],
        candidates: Sequence[ExtractionCandidate],
        decisions: Sequence[FactVerificationDecisionModel],
    ) -> None:
        fields = [candidate.field_name for candidate in candidates]
        if len(fields) != len(set(fields)):
            raise FactLifecycleError("promotion cannot contain duplicate fact fields")
        target = (
            runs[0].source_bundle_revision_id,
            runs[0].target_scope,
            runs[0].opportunity_id,
            runs[0].opportunity_version,
            runs[0].opportunity_unit_id,
            runs[0].opportunity_unit_version_id,
        )
        for run, candidate, decision in zip(runs, candidates, decisions, strict=True):
            if (
                run.source_bundle_revision_id,
                run.target_scope,
                run.opportunity_id,
                run.opportunity_version,
                run.opportunity_unit_id,
                run.opportunity_unit_version_id,
            ) != target:
                raise FactLifecycleError(
                    "promotion candidates must share an exact target and bundle"
                )
            if candidate.abstained:
                if decision.decision != "UNKNOWN":
                    raise FactLifecycleError("abstained candidate requires UNKNOWN decision")
            elif decision.decision != "APPROVE":
                raise FactLifecycleError("known fact requires APPROVE decision")


__all__ = [
    "FactLifecycleError",
    "FactLifecycleService",
    "ensure_independent_verification",
    "extraction_input_block_set_hash",
]
