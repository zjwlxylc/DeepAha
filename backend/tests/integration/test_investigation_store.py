"""Synthetic integration checks; non-synthetic flags exercise auth, not human acceptance."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.investigations.contracts import (
    CreateInvestigation,
    InvestigationError,
    ReviewInvestigation,
)
from deepaha.investigations.delivery import ValidatedDelivery, validate_delivery
from deepaha.investigations.models import (
    InvestigationEvent,
    InvestigationMaterial,
    InvestigationTask,
)
from deepaha.investigations.prompt import frozen_contract
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import HumanReviewError
from deepaha.opportunities.models import Opportunity
from deepaha.p9b.models import VerifiedFact
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
)
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint
from tests.investigations.test_delivery import _sample

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 7, 10, tzinfo=UTC)
BUCKET = "investigation-test"


@dataclass
class MutableClock:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value


@dataclass
class StoreHarness:
    store: InvestigationStore
    factory: sessionmaker[Session]
    objects: LocalFileObjectStore
    object_root: Path
    clock: MutableClock
    command: CreateInvestigation
    principal: ReviewerPrincipal


@pytest.fixture
def harness(migrated_engine: Engine, tmp_path: Path) -> StoreHarness:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    source_id, endpoint_id, reviewer_id = uuid7(), uuid7(), uuid7()
    roles = frozenset({ReviewerRole.LOCAL_TEST_OPERATOR, ReviewerRole.VALIDATION_REVIEWER})
    principal = ReviewerPrincipal(
        reviewer_id, roles, frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}), False
    )
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id=f"src_{source_id.hex}",
                canonical_url="https://example.gov/",
                authority_name="Synthetic issuer",
                tier="OFFICIAL_PRIMARY",
                jurisdiction="Synthetic region",
                active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            ReviewerAccountModel(
                reviewer_id=reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"test-only-reviewer-{reviewer_id.hex}",
                roles=[role.value for role in roles],
                allowed_purposes=[OPPORTUNITY_FACT_VALIDATION_PURPOSE],
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            SourceEndpoint(
                endpoint_id=endpoint_id,
                source_id=source_id,
                url="https://example.gov/notice",
                allowed_hosts=["example.gov"],
                expected_media_types=["text/html"],
                browser_policy="NEVER",
                minimum_interval_seconds=1,
                timeout_seconds=5,
                max_attempts=1,
                robots_url=None,
                robots_decision="ALLOWED",
                robots_checked_at=NOW,
                content_use_basis="OFFICIAL_PUBLIC_ACCESS",
                license_name=None,
                license_url=None,
                attribution=None,
                fixture_storage_allowed=False,
                usage_note="Synthetic bytes only; no real site or human acceptance evidence.",
                policy_version="synthetic-policy-1",
                active=True,
                verified_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    objects = LocalFileObjectStore(root=tmp_path, bucket=BUCKET)
    objects.ensure_bucket()
    clock = MutableClock()
    command = CreateInvestigation(
        source_id=source_id,
        endpoint_id=endpoint_id,
        notice_url="https://example.gov/notice",
        brief="Investigate only the supplied synthetic notice.",
        expected_entity_keys=("position",),
        wall_time_seconds=60,
    )
    return StoreHarness(
        InvestigationStore(factory, objects, clock),
        factory,
        objects,
        tmp_path,
        clock,
        command,
        principal,
    )


def _files(
    task_id: UUID, *, seed_url: str = "https://example.gov/notice"
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    opportunities, evidence, artifacts = _sample()
    for document in (opportunities, evidence):
        document.update(case_id=str(task_id), seed_url=seed_url)
    return {
        "opportunities.json": json.dumps(opportunities).encode(),
        "evidence.json": json.dumps(evidence).encode(),
        "report.md": b"Synthetic fixture, not a human acceptance result.",
    }, artifacts


def _collecting(h: StoreHarness, command: CreateInvestigation | None = None) -> tuple[UUID, UUID]:
    task_id = h.store.create(command or h.command, h.principal, "register-synthetic-task")
    owner = uuid7()
    h.store.claim(task_id, owner, {"agent": "synthetic-agent", "version": "test-1"})
    h.store.transition(task_id, owner, "PREPARING", ("test-runtime", "test-session"))
    h.store.transition(task_id, owner, "INVESTIGATING")
    h.store.transition(task_id, owner, "COLLECTING")
    return task_id, owner


def _pending(h: StoreHarness) -> tuple[UUID, ValidatedDelivery, dict[str, bytes]]:
    task_id, owner = _collecting(h)
    files, artifacts = _files(task_id)
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task_id, owner, files)
    h.store.finish(task_id, owner, delivery, files)
    return task_id, delivery, artifacts


def _review(delivery: ValidatedDelivery) -> ReviewInvestigation:
    return ReviewInvestigation(
        decision="APPROVE",
        delivery_hash=delivery.sha256,
        reason="Synthetic integration fixture decision; no human acceptance claim.",
    )


def _count(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_runtime_checkpoint_can_add_session_once_and_then_remains_immutable(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "partial-remote-creation")
    owner = uuid7()
    h.store.claim(task_id, owner, {"provider": "SYNTHETIC_TEST"})
    h.store.transition(task_id, owner, "CREATING", ("test-runtime", None))
    assert h.store.get(task_id)["remote_session_id"] is None
    h.store.transition(task_id, owner, "CREATING", ("test-runtime", "test-session"))
    assert h.store.get(task_id)["remote_session_id"] == "test-session"
    for column in ("runtime_id", "remote_session_id"):
        with pytest.raises(DBAPIError), h.factory.begin() as session:
            session.execute(
                text(f"UPDATE investigation_tasks SET {column} = NULL WHERE task_id = :id"),
                {"id": task_id},
            )


def test_expired_checkpoint_persists_without_extending_deadline_or_replacing_ids(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "expired-checkpoint")
    owner = uuid7()
    h.store.claim(task_id, owner, {"provider": "SYNTHETIC_TEST"})
    with h.factory() as session:
        original = session.get(InvestigationTask, task_id)
        assert original is not None
        deadline, lease = original.deadline_at, original.lease_until
    h.clock.value += timedelta(seconds=61)
    h.store.checkpoint_remote(task_id, owner, "test-runtime", None)
    h.store.checkpoint_remote(task_id, owner, "test-runtime", "test-session")
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None
        assert (task.runtime_id, task.remote_session_id) == ("test-runtime", "test-session")
        assert (task.deadline_at, task.lease_until, task.lease_owner) == (deadline, lease, owner)
        assert task.status == "CREATING"
        event_count = _count(session, InvestigationEvent)
    h.store.checkpoint_remote(task_id, owner, "test-runtime", None)
    h.store.checkpoint_remote(task_id, owner, "test-runtime", "test-session")
    with h.factory() as session:
        assert _count(session, InvestigationEvent) == event_count
    with pytest.raises(InvestigationError, match="TASK_DEADLINE_EXCEEDED"):
        h.store.transition(task_id, owner, "PREPARING")
    with pytest.raises(InvestigationError, match="TASK_LEASE_LOST"):
        h.store.checkpoint_remote(task_id, uuid7(), "test-runtime", "test-session")
    with pytest.raises(InvestigationError, match="WMA_REMOTE_BINDING_IMMUTABLE"):
        h.store.checkpoint_remote(task_id, owner, "other-runtime", "test-session")


def test_legacy_contract_recovery_preserves_original_immutable_receipt(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deepaha.investigations import store as store_module

    h = harness
    legacy = copy.deepcopy(frozen_contract())
    legacy["version"] = "direct-wma-intake/1"
    legacy["prompt_sha256"] = "c" * 64
    with monkeypatch.context() as old_version:
        old_version.setattr(store_module, "frozen_contract", lambda: legacy)
        task_id, owner = _collecting(h)
        h.store.fail(task_id, owner, "COLLECTION_RETRYABLE", "SYNTHETIC_DOWNLOAD_FAILED")
    original_hash = h.store.get(task_id)["contract_hash"]
    recovery_owner = uuid7()
    recovered = h.store.claim(task_id, recovery_owner, {"prompt_limit": 0}, recover=True)
    assert recovered["status"] == "COLLECTING"
    assert recovered["runtime_id"] == "test-runtime"
    files, artifacts = _files(task_id)
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task_id, recovery_owner, files)
    h.store.finish(task_id, recovery_owner, delivery, files)
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and task.contract == legacy
        assert task.contract_hash == original_hash
        assert task.status == "PENDING_REVIEW"
        assert task.delivery_hash == delivery.sha256


def test_binding_receipt_preserves_execution_and_cannot_be_replaced(harness: StoreHarness) -> None:
    h = harness
    task_id = h.store.create(h.command, h.principal, "binding-receipt")
    owner = uuid7()
    original: dict[str, object] = {
        "provider": "SYNTHETIC_TEST",
        "published_release": {"version": "v1"},
    }
    h.store.claim(task_id, owner, original)
    h.store.transition(task_id, owner, "PREPARING", ("test-runtime", "test-session"))
    receipt: dict[str, object] = {
        "session_binding": "SYNTHETIC_TEST",
        "model_configuration": "synthetic-model",
    }
    h.store.record_binding(task_id, owner, receipt)
    h.store.record_binding(task_id, owner, receipt)
    assert h.store.get(task_id)["execution"] == original | {"binding": receipt}
    with pytest.raises(InvestigationError, match="WMA_BINDING_EVIDENCE_IMMUTABLE"):
        h.store.record_binding(task_id, owner, {"model_configuration": "other"})
    for expression in ("execution - 'binding'", "'{}'::jsonb"):
        with pytest.raises(DBAPIError), h.factory.begin() as session:
            session.execute(
                text(
                    f"UPDATE investigation_tasks SET execution = {expression} WHERE task_id = :id"
                ),
                {"id": task_id},
            )


def test_duplicate_registration_serializes_and_rejects_changed_payload(
    harness: StoreHarness,
) -> None:
    h = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = tuple(
            pool.map(lambda _: h.store.create(h.command, h.principal, "same-request-key"), range(2))
        )
    assert ids[0] == ids[1]
    with pytest.raises(InvestigationError, match="IDEMPOTENCY_CONFLICT"):
        h.store.create(
            h.command.model_copy(update={"brief": "changed"}), h.principal, "same-request-key"
        )
    with h.factory() as session:
        assert _count(session, InvestigationTask) == 1
        assert _count(session, InvestigationEvent) == 1


@pytest.mark.parametrize(
    "invalid",
    [
        "source_inactive",
        "secondary",
        "link_only",
        "outside",
        "attachment_outside",
        "http",
        "credentials",
    ],
)
def test_registration_requires_approved_source_and_every_url_in_scope(
    harness: StoreHarness,
    invalid: str,
) -> None:
    h = harness
    command = h.command
    with h.factory.begin() as session:
        source = session.get(Source, command.source_id)
        endpoint = session.get(SourceEndpoint, command.endpoint_id)
        assert source is not None and endpoint is not None
        if invalid == "source_inactive":
            source.active = False
        elif invalid == "secondary":
            source.tier = "TRUSTED_SECONDARY"
        elif invalid == "link_only":
            endpoint.content_use_basis = "LINK_ONLY"
    if invalid in {"outside", "http", "credentials"}:
        url = {
            "outside": "https://other.example/notice",
            "http": "http://example.gov/notice",
            "credentials": "https://name:secret@example.gov/notice",
        }[invalid]
        command = command.model_copy(update={"notice_url": url})
    elif invalid == "attachment_outside":
        command = command.model_copy(
            update={"expected_artifact_urls": ("https://other.example/a",)}
        )
    with pytest.raises(InvestigationError):
        h.store.create(command, h.principal, "invalid-request")
    with h.factory() as session:
        assert _count(session, InvestigationTask) == 0


def test_live_lease_cannot_be_stolen_and_expiry_only_allows_recollection(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, owner = _collecting(h)
    with pytest.raises(InvestigationError, match="TASK_ALREADY_RUNNING"):
        h.store.claim(task_id, uuid7(), {"attempt": "duplicate"})
    h.clock.value += timedelta(seconds=66)
    with pytest.raises(InvestigationError, match="NEW_PROMPT_FORBIDDEN"):
        h.store.claim(task_id, uuid7(), {"attempt": "new-prompt"})
    recovered_owner = uuid7()
    recovered = h.store.claim(task_id, recovered_owner, {"attempt": "recollect"}, recover=True)
    assert recovered["status"] == "COLLECTING"
    assert recovered["runtime_id"] == "test-runtime"
    assert recovered["remote_session_id"] == "test-session"
    with pytest.raises(InvestigationError, match="TASK_LEASE_LOST"):
        h.store.transition(task_id, owner, "COLLECTING")


def test_restart_keeps_original_manifest_and_rejects_changed_recovery(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, owner = _collecting(h)
    files, _ = _files(task_id)
    h.store.freeze_manifest(task_id, owner, files)
    h.store.fail(task_id, owner, "COLLECTION_RETRYABLE", "SYNTHETIC_RECOVERY_NEEDED")
    restarted = InvestigationStore(h.factory, h.objects, h.clock)
    next_owner = uuid7()
    restarted.claim(task_id, next_owner, {"attempt": "recollect"}, recover=True)
    restarted.freeze_manifest(task_id, next_owner, files)
    with pytest.raises(InvestigationError, match="RECOVERED_MANIFEST_CHANGED"):
        restarted.freeze_manifest(task_id, next_owner, files | {"report.md": b"different report"})


def test_finish_preserves_bytes_without_fabricating_fetch_or_promoting_facts(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, delivery, originals = _pending(h)
    view = InvestigationStore(h.factory, h.objects, h.clock).get(task_id)
    assert view["status"] == "PENDING_REVIEW"
    assert view["delivery_hash"] == delivery.sha256
    assert [task["task_id"] for task in h.store.list_tasks()] == [str(task_id)]
    with h.factory() as session:
        material = session.scalar(select(InvestigationMaterial))
        assert material is not None
        raw = session.get(RawArtifact, material.raw_artifact_id)
        assert raw is not None
        assert raw.http_status is None
        assert raw.content_sha256 == sha256(originals["notice"]).hexdigest()
        assert h.objects.get_bytes(key=raw.object_key) == originals["notice"]
        assert material.metadata_snapshot["url_provenance"] == "AGENT_DECLARED"
        for model in (
            CaptureObservation,
            AcquisitionEvaluation,
            AcquisitionRun,
            Opportunity,
            VerifiedFact,
        ):
            assert _count(session, model) == 0


@pytest.mark.parametrize(
    "missing,code",
    [("material", "EXPECTED_MATERIAL_MISSING"), ("entity", "EXPECTED_ENTITY_MISSING")],
)
def test_finish_cannot_hide_missing_expected_material_or_entity(
    harness: StoreHarness,
    missing: str,
    code: str,
) -> None:
    h = harness
    change = (
        {"expected_artifact_urls": ("https://example.gov/required.pdf",)}
        if missing == "material"
        else {"expected_entity_keys": ("missing-position",)}
    )
    task_id, owner = _collecting(h, h.command.model_copy(update=change))
    files, artifacts = _files(task_id)
    h.store.freeze_manifest(task_id, owner, files)
    with pytest.raises(InvestigationError, match=code):
        h.store.finish(task_id, owner, validate_delivery(files, artifacts), files)
    with h.factory() as session:
        assert _count(session, RawArtifact) == 0
        assert _count(session, InvestigationMaterial) == 0
    assert h.store.get(task_id)["status"] == "COLLECTING"


@pytest.mark.parametrize("wrong", ["task", "seed"])
def test_finish_binds_both_json_documents_to_actual_task_and_notice(
    harness: StoreHarness,
    wrong: str,
) -> None:
    h = harness
    task_id, owner = _collecting(h)
    files, artifacts = _files(task_id)
    evidence = json.loads(files["evidence.json"])
    evidence["case_id" if wrong == "task" else "seed_url"] = (
        str(uuid7()) if wrong == "task" else "https://example.gov/different-notice"
    )
    files["evidence.json"] = json.dumps(evidence).encode()
    h.store.freeze_manifest(task_id, owner, files)
    with pytest.raises(InvestigationError, match="DELIVERY_TASK_BINDING_MISMATCH"):
        h.store.finish(task_id, owner, validate_delivery(files, artifacts), files)


@pytest.mark.parametrize(
    "invalid",
    ["principal_synthetic", "account_synthetic", "inactive", "account_role", "account_missing"],
)
def test_review_rechecks_persisted_identity_instead_of_trusting_principal_flags(
    harness: StoreHarness,
    invalid: str,
) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    principal = h.principal
    if invalid == "principal_synthetic":
        principal = replace(principal, synthetic=True)
    elif invalid == "account_missing":
        principal = replace(principal, reviewer_id=uuid7())
    else:
        with h.factory.begin() as session:
            account = session.get(ReviewerAccountModel, principal.reviewer_id)
            assert account is not None
            if invalid == "account_synthetic":
                account.synthetic = True
            elif invalid == "inactive":
                account.active = False
            else:
                account.roles = [ReviewerRole.LOCAL_TEST_OPERATOR.value]
    with pytest.raises((InvestigationError, HumanReviewError, ReviewerAuthenticationError)):
        h.store.review(task_id, _review(delivery), principal, "synthetic-review")
    view = h.store.get(task_id)
    assert view["status"] == "PENDING_REVIEW" and view["review"] is None


def test_review_hash_cas_and_repeated_receipt_do_not_promote_formal_entities(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    command = _review(delivery)
    with pytest.raises(InvestigationError, match="REVIEW_DELIVERY_CONFLICT"):
        h.store.review(
            task_id,
            command.model_copy(update={"delivery_hash": "0" * 64}),
            h.principal,
            "wrong-version",
        )
    first = h.store.review(task_id, command, h.principal, "synthetic-review")
    repeated = h.store.review(task_id, command, h.principal, "synthetic-review")
    assert repeated == first
    assert first["status"] == "APPROVED"
    assert first["review"]["scope"] == "INTERNAL_INTAKE_ONLY"
    with pytest.raises(InvestigationError, match="REVIEW_ALREADY_DECIDED"):
        h.store.review(
            task_id,
            command.model_copy(update={"decision": "REJECT"}),
            h.principal,
            "synthetic-review",
        )
    with h.factory() as session:
        assert _count(session, Opportunity) == 0
        assert _count(session, VerifiedFact) == 0
        approvals = session.scalars(
            select(InvestigationEvent).where(
                InvestigationEvent.task_id == task_id, InvestigationEvent.status == "APPROVED"
            )
        ).all()
        assert len(approvals) == 1


def test_review_rejects_stored_original_corruption(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    with h.factory() as session:
        raw = session.scalar(select(RawArtifact))
        assert raw is not None
        path = h.object_root / BUCKET / "objects" / raw.object_key
    path.write_bytes(b"tampered synthetic original")
    with pytest.raises((InvestigationError, ObjectIntegrityError)):
        h.store.review(task_id, _review(delivery), h.principal, "synthetic-review")
    assert h.store.get(task_id)["status"] == "PENDING_REVIEW"
