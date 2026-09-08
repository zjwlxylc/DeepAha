from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from deepaha.artifacts.object_store import ObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.investigations.contracts import (
    BindInvestigation,
    CreateInvestigation,
    InvestigationError,
    ReviewInvestigation,
    allowed_url,
    digest,
)
from deepaha.investigations.delivery import ValidatedDelivery
from deepaha.investigations.models import (
    InvestigationEvent,
    InvestigationMaterial,
    InvestigationTask,
)
from deepaha.investigations.prompt import frozen_contract, require_recovery_contract
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
)
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import Source, SourceEndpoint


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvestigationStore:
    def __init__(
        self,
        factory: Callable[[], Session],
        objects: ObjectStore,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory = factory
        self.objects = objects
        self.clock = clock

    def _get(self, session: Session, task_id: UUID, *, lock: bool = False) -> InvestigationTask:
        query = select(InvestigationTask).where(InvestigationTask.task_id == task_id)
        if lock:
            query = query.with_for_update()
        task = session.scalar(query)
        if task is None:
            raise InvestigationError("INVESTIGATION_NOT_FOUND")
        return task

    def _event(
        self, session: Session, task: InvestigationTask, status: str, error: str | None = None
    ) -> None:
        task.status, task.error_code, task.updated_at = status, error, self.clock()
        sequence = (
            session.scalar(
                select(func.max(InvestigationEvent.sequence)).where(
                    InvestigationEvent.task_id == task.task_id
                )
            )
            or 0
        )
        session.add(
            InvestigationEvent(
                task_id=task.task_id,
                sequence=sequence + 1,
                status=status,
                error_code=error,
                created_at=task.updated_at,
            )
        )

    def _source(self, session: Session, command: CreateInvestigation) -> dict[str, Any]:
        source = session.get(Source, command.source_id)
        endpoint = session.get(SourceEndpoint, command.endpoint_id)
        if (
            source is None
            or endpoint is None
            or not source.active
            or not endpoint.active
            or endpoint.source_id != source.source_id
            or source.tier != "OFFICIAL_PRIMARY"
            or endpoint.robots_decision not in ("ALLOWED", "NOT_APPLICABLE")
            or endpoint.content_use_basis not in ("OFFICIAL_PUBLIC_ACCESS", "OPEN_LICENSE")
        ):
            raise InvestigationError("APPROVED_SOURCE_REQUIRED")
        if any(
            not allowed_url(url, endpoint.allowed_hosts)
            for url in (command.notice_url, *command.expected_artifact_urls)
        ):
            raise InvestigationError("NOTICE_OUTSIDE_APPROVED_HOSTS")
        return {
            "allowed_hosts": endpoint.allowed_hosts,
            "policy_version": endpoint.policy_version,
            "authority_name": source.authority_name,
            "tier": source.tier,
            "robots_decision": endpoint.robots_decision,
            "content_use_basis": endpoint.content_use_basis,
        }

    def create(self, command: CreateInvestigation, principal: ReviewerPrincipal, key: str) -> UUID:
        require_reviewer_authority(
            principal, ReviewerRole.LOCAL_TEST_OPERATOR, OPPORTUNITY_FACT_VALIDATION_PURPOSE
        )
        key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
        request = command.model_dump(mode="json")
        request_hash = digest(request)
        with self.factory() as session, session.begin():
            # Same principal/key is serialized before insertion, including a lost receipt retry.
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key_hash[:15], 16)}
            )
            previous = session.scalar(
                select(InvestigationTask).where(
                    InvestigationTask.created_by == principal.reviewer_id,
                    InvestigationTask.request_key_hash == key_hash,
                )
            )
            if previous is not None:
                if previous.request_hash != request_hash:
                    raise InvestigationError("IDEMPOTENCY_CONFLICT")
                return previous.task_id
            source = self._source(session, command)
            contract = frozen_contract()
            now = self.clock()
            task = InvestigationTask(
                task_id=uuid7(),
                source_id=command.source_id,
                endpoint_id=command.endpoint_id,
                created_by=principal.reviewer_id,
                request_key_hash=key_hash,
                request_hash=request_hash,
                request=request,
                source_snapshot=source,
                contract=contract,
                contract_hash=digest(contract),
                status="QUEUED",
                execution={},
                result_objects={},
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.flush()
            self._event(session, task, "QUEUED")
            return task.task_id

    def claim(
        self, task_id: UUID, owner: UUID, execution: dict[str, object], *, recover: bool = False
    ) -> dict[str, Any]:
        with self.factory() as session, session.begin():
            task = self._get(session, task_id, lock=True)
            now = self.clock()
            if task.status in ("PENDING_REVIEW", "APPROVED", "REJECTED"):
                return self._view(session, task)
            if task.lease_until is not None and now <= task.lease_until:
                raise InvestigationError("TASK_ALREADY_RUNNING")
            command = CreateInvestigation.model_validate(task.request)
            if digest(self._source(session, command)) != digest(task.source_snapshot):
                raise InvestigationError("SOURCE_POLICY_CHANGED")
            if recover:
                require_recovery_contract(task.contract, task.contract_hash)
                if (
                    not task.runtime_id
                    or not task.remote_session_id
                    or task.status
                    not in (
                        "INVESTIGATING",
                        "EXECUTION_UNCERTAIN",
                        "COLLECTING",
                        "COLLECTION_RETRYABLE",
                        "EXPIRED",
                    )
                ):
                    raise InvestigationError("TASK_NOT_RECOVERABLE")
                status, seconds = "COLLECTING", 120
                task.execution = dict(task.execution) | {"recovery": execution}
            else:
                if (
                    digest(task.contract) != task.contract_hash
                    or digest(frozen_contract()) != task.contract_hash
                ):
                    raise InvestigationError("TASK_CONTRACT_CHANGED")
                if task.status != "QUEUED":
                    raise InvestigationError("NEW_PROMPT_FORBIDDEN")
                task.execution = execution
                status, seconds = "CREATING", command.wall_time_seconds
            task.lease_owner = owner
            task.deadline_at = now + timedelta(seconds=seconds)
            task.lease_until = task.deadline_at + timedelta(seconds=5)
            self._event(session, task, status)
            session.flush()
            return self._view(session, task)

    def _owned(
        self, session: Session, task_id: UUID, owner: UUID, *, allow_expired: bool = False
    ) -> InvestigationTask:
        task = self._get(session, task_id, lock=True)
        if task.lease_owner != owner:
            raise InvestigationError("TASK_LEASE_LOST")
        if not allow_expired and (task.deadline_at is None or self.clock() >= task.deadline_at):
            raise InvestigationError("TASK_DEADLINE_EXCEEDED")
        return task

    def transition(
        self, task_id: UUID, owner: UUID, status: str, remote: tuple[str, str | None] | None = None
    ) -> None:
        with self.factory() as session, session.begin():
            task = self._owned(session, task_id, owner)
            if remote:
                task.runtime_id, task.remote_session_id = remote
            self._event(session, task, status)

    def checkpoint_remote(
        self, task_id: UUID, owner: UUID, runtime_id: str, session_id: str | None
    ) -> None:
        """Remember already-created resources, including just after the deadline."""
        with self.factory() as session, session.begin():
            task = self._owned(session, task_id, owner, allow_expired=True)
            if task.status != "CREATING":
                raise InvestigationError("WMA_CHECKPOINT_NOT_CREATING")
            if not runtime_id or session_id == "":
                raise InvestigationError("WMA_CHECKPOINT_INVALID")
            if (task.runtime_id is not None and task.runtime_id != runtime_id) or (
                session_id is not None
                and task.remote_session_id is not None
                and task.remote_session_id != session_id
            ):
                raise InvestigationError("WMA_REMOTE_BINDING_IMMUTABLE")
            resolved_session = task.remote_session_id if session_id is None else session_id
            if (task.runtime_id, task.remote_session_id) == (runtime_id, resolved_session):
                return
            task.runtime_id, task.remote_session_id = runtime_id, resolved_session
            # Deadline, lease, execution configuration and stage are not extended.
            self._event(session, task, "CREATING")

    def record_binding(self, task_id: UUID, owner: UUID, evidence: dict[str, object]) -> None:
        with self.factory() as session, session.begin():
            task = self._owned(session, task_id, owner)
            if not task.runtime_id or not task.remote_session_id or task.status != "PREPARING":
                raise InvestigationError("WMA_BINDING_NOT_READY")
            previous = task.execution.get("binding")
            if previous is not None and digest(previous) != digest(evidence):
                raise InvestigationError("WMA_BINDING_EVIDENCE_IMMUTABLE")
            task.execution = dict(task.execution) | {"binding": evidence}

    def fail(self, task_id: UUID, owner: UUID, status: str, code: str) -> None:
        with self.factory() as session, session.begin():
            task = self._owned(session, task_id, owner, allow_expired=True)
            if task.status in ("PENDING_REVIEW", "APPROVED", "REJECTED"):
                return
            self._event(session, task, status, code)
            task.lease_owner = task.lease_until = None

    def finish(
        self,
        task_id: UUID,
        owner: UUID,
        delivery: ValidatedDelivery,
        result_files: dict[str, bytes],
    ) -> None:
        with self.factory() as session, session.begin():
            task = self._owned(session, task_id, owner)
            command = CreateInvestigation.model_validate(task.request)
            source = self._source(session, command)
            if digest(source) != digest(task.source_snapshot):
                raise InvestigationError("SOURCE_POLICY_CHANGED")
            for data in (delivery.opportunities, delivery.evidence):
                if (
                    data.get("case_id") != str(task_id)
                    or data.get("seed_url") != command.notice_url
                ):
                    raise InvestigationError("DELIVERY_TASK_BINDING_MISMATCH")
            urls = {item.url for item in delivery.artifacts}
            if command.notice_url not in urls or not set(command.expected_artifact_urls).issubset(
                urls
            ):
                raise InvestigationError("EXPECTED_MATERIAL_MISSING")
            if not set(command.expected_entity_keys).issubset(
                {f.entity_id for f in delivery.facts}
            ):
                raise InvestigationError("EXPECTED_ENTITY_MISSING")
            for item in delivery.artifacts:
                if not allowed_url(item.url, source["allowed_hosts"]):
                    raise InvestigationError("MATERIAL_OUTSIDE_APPROVED_HOSTS")
                imported = import_raw_artifact(
                    session=session,
                    object_store=self.objects,
                    command=ImportRawArtifactCommand(
                        source_id=task.source_id,
                        requested_url=item.url,
                        resolved_url=item.url,
                        retrieved_at=self.clock(),
                        http_status=None,
                        media_type=item.media_type,
                        content=item.content,
                        collector_version="direct-wma-delivery/1",
                        metadata_schema_version="1",
                    ),
                    reuse_content_identity=True,
                )
                session.add(
                    InvestigationMaterial(
                        task_id=task_id,
                        material_id=item.artifact_id,
                        raw_artifact_id=imported.artifact.artifact_id,
                        metadata_snapshot={
                            "artifact_id": item.artifact_id,
                            "url": item.url,
                            "sha256": item.sha256,
                            "media_type": item.media_type,
                            "size_bytes": len(item.content),
                            "remote_path": item.remote_path,
                            "url_provenance": "AGENT_DECLARED",
                            "receipt_at": self.clock().isoformat(),
                        },
                    )
                )
            keys = {}
            for name, content in result_files.items():
                raw_hash = sha256(content).hexdigest()
                key = f"investigations/sha256/{raw_hash[:2]}/{raw_hash}"
                self.objects.put_bytes_if_absent(
                    key=key, content=content, media_type="application/octet-stream", sha256=raw_hash
                )
                keys[name] = key
            if task.result_objects and task.result_objects != keys:
                raise InvestigationError("RECOVERED_MANIFEST_CHANGED")
            self._owned(session, task_id, owner)
            task.result_objects = keys
            task.delivery_hash = delivery.sha256
            task.delivery = {
                "opportunities": delivery.opportunities,
                "evidence": delivery.evidence,
                "report": delivery.report,
                "facts": [asdict(f) for f in delivery.facts],
                "issues": list(delivery.issues),
                "material_count": len(delivery.artifacts),
                "entity_count": len({f.entity_id for f in delivery.facts}),
            }
            self._event(session, task, "PENDING_REVIEW")
            task.lease_owner = task.lease_until = None

    def review(
        self, task_id: UUID, command: ReviewInvestigation, principal: ReviewerPrincipal, key: str
    ) -> dict[str, Any]:
        require_human_fact_reviewer(principal)
        key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
        request_hash = digest(command.model_dump(mode="json"))
        with self.factory() as session, session.begin():
            account = session.get(ReviewerAccountModel, principal.reviewer_id)
            if account is None or not account.active or account.synthetic:
                raise InvestigationError("HUMAN_VALIDATION_AUTHORITY_REQUIRED")
            require_human_fact_reviewer(
                ReviewerPrincipal(
                    account.reviewer_id,
                    frozenset(ReviewerRole(role) for role in account.roles),
                    frozenset(account.allowed_purposes),
                    account.synthetic,
                )
            )
            task = self._get(session, task_id, lock=True)
            if task.review is not None:
                if (
                    task.review_key_hash == key_hash
                    and task.review_hash == request_hash
                    and task.reviewer_id == principal.reviewer_id
                ):
                    return self._view(session, task)
                raise InvestigationError("REVIEW_ALREADY_DECIDED")
            if task.status != "PENDING_REVIEW" or command.delivery_hash != task.delivery_hash:
                raise InvestigationError("REVIEW_DELIVERY_CONFLICT")
            # Detect storage loss or alteration before accepting a decision.
            self._verify_stored_bytes(session, task)
            task.review = {
                "decision": command.decision,
                "reason": command.reason,
                "reviewer_id": str(principal.reviewer_id),
                "created_at": self.clock().isoformat(),
                "scope": "INTERNAL_INTAKE_ONLY",
            }
            task.review_key_hash, task.review_hash = key_hash, request_hash
            task.reviewer_id = principal.reviewer_id
            self._event(session, task, "APPROVED" if command.decision == "APPROVE" else "REJECTED")
            session.flush()
            return self._view(session, task)

    def _verify_stored_bytes(self, session: Session, task: InvestigationTask) -> None:
        from deepaha.artifacts.models import RawArtifact

        for material in session.scalars(
            select(InvestigationMaterial).where(InvestigationMaterial.task_id == task.task_id)
        ):
            raw = session.get(RawArtifact, material.raw_artifact_id)
            if (
                raw is None
                or sha256(self.objects.get_bytes(key=raw.object_key)).hexdigest()
                != material.metadata_snapshot["sha256"]
            ):
                raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
        for key in task.result_objects.values():
            if sha256(self.objects.get_bytes(key=key)).hexdigest() != key.rsplit("/", 1)[-1]:
                raise InvestigationError("STORED_RESULT_INTEGRITY_FAILED")

    def freeze_manifest(self, task_id: UUID, owner: UUID, files: dict[str, bytes]) -> None:
        with self.factory() as session, session.begin():
            task = self._owned(session, task_id, owner)
            keys = {}
            for name, content in files.items():
                raw_hash = sha256(content).hexdigest()
                key = f"investigations/sha256/{raw_hash[:2]}/{raw_hash}"
                self.objects.put_bytes_if_absent(
                    key=key, content=content, media_type="application/octet-stream", sha256=raw_hash
                )
                keys[name] = key
            if task.result_objects and task.result_objects != keys:
                raise InvestigationError("RECOVERED_MANIFEST_CHANGED")
            self._owned(session, task_id, owner)
            task.result_objects = keys

    def _view(
        self, session: Session, task: InvestigationTask, *, include_documents: bool = True
    ) -> dict[str, Any]:
        from deepaha.investigations.bindings import describe_bindings
        from deepaha.investigations.documents import describe_documents

        materials = list(
            session.scalars(
                select(InvestigationMaterial)
                .where(InvestigationMaterial.task_id == task.task_id)
                .order_by(InvestigationMaterial.material_id)
            )
        )
        delivery = cast(dict[str, Any], task.delivery or {})
        # Older snapshots retained notes in the original bundle but omitted them
        # from the materialized facts. Restore them in the read view only.
        original_notes = {
            (fact["entity_id"], fact["field"]): fact.get("note")
            for fact in delivery.get("evidence", {}).get("facts_flat", [])
        }
        facts = [
            fact
            | {"note": fact.get("note", original_notes.get((fact["entity_id"], fact["field"])))}
            for fact in delivery.get("facts", [])
        ]
        bindings = describe_bindings(session, task) if include_documents else []
        return dict(task.request) | {
            "task_id": str(task.task_id),
            "status": task.status,
            "error_code": task.error_code,
            "created_at": task.created_at.astimezone(UTC).isoformat(),
            "updated_at": task.updated_at.astimezone(UTC).isoformat(),
            "contract_hash": task.contract_hash,
            "delivery_hash": task.delivery_hash,
            "issues": delivery.get("issues", []),
            "opportunities": delivery.get("opportunities"),
            "facts": facts,
            "report": delivery.get("report"),
            "materials": [m.metadata_snapshot for m in materials],
            "document_preparation": (
                describe_documents(session, materials) if delivery and include_documents else None
            ),
            "review": task.review,
            "entity_binding": bindings[0] if bindings else None,
            "binding_history": bindings,
            "binding_entities": delivery.get("evidence", {}).get("entities", [])
            if include_documents
            else [],
            "execution": task.execution,
            "runtime_id": task.runtime_id,
            "remote_session_id": task.remote_session_id,
            "deadline_at": (
                None if task.deadline_at is None else task.deadline_at.astimezone(UTC).isoformat()
            ),
            "source_snapshot": task.source_snapshot,
        }

    def get(self, task_id: UUID) -> dict[str, Any]:
        with self.factory() as session:
            return self._view(session, self._get(session, task_id))

    def prepare_documents(
        self, task_id: UUID, delivery_hash: str, principal: ReviewerPrincipal
    ) -> dict[str, Any]:
        from deepaha.investigations.documents import prepare_documents

        prepare_documents(self, task_id, delivery_hash, principal)
        return self.get(task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.factory() as session:
            return [
                self._view(session, task, include_documents=False)
                for task in session.scalars(
                    select(InvestigationTask)
                    .order_by(InvestigationTask.created_at.desc())
                    .limit(100)
                )
            ]

    def bind(
        self, task_id: UUID, command: BindInvestigation, principal: ReviewerPrincipal, key: str
    ) -> dict[str, Any]:
        from deepaha.investigations.bindings import bind

        return bind(self, task_id, command, principal, key)
