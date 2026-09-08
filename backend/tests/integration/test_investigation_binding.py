"""Synthetic identity decisions exercise engineering boundaries, not human acceptance."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import UUID, uuid7

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.documents.models import Document, EvidenceRef
from deepaha.investigations.contracts import BindInvestigation, InvestigationError
from deepaha.investigations.delivery import ValidatedDelivery
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.identity import OpportunityUnitService, UnitSeed
from deepaha.p9b.models import SourceBundleMember, SourceBundleRevision, VerifiedFact
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import CaptureObservation
from tests.integration.test_investigation_store import (
    NOW,
    StoreHarness,
    _count,
    _pending,
    _review,
    harness,
)

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def _prepared(h: StoreHarness, *, approved: bool = True) -> tuple[UUID, ValidatedDelivery, UUID]:
    task_id, delivery, _ = _pending(h)
    h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    if approved:
        h.store.review(task_id, _review(delivery), h.principal, "synthetic-review")
    return task_id, delivery, _target(h)


def _target(h: StoreHarness) -> UUID:
    with h.factory.begin() as session:
        doc = session.scalar(select(Document))
        assert doc is not None
        ref = session.scalar(select(EvidenceRef).where(EvidenceRef.document_id == doc.document_id))
        assert ref is not None
        identity = uuid7()
        session.add(
            Opportunity(
                opportunity_id=identity,
                public_id=f"opp_{identity.hex}",
                type="PUBLIC_INSTITUTION_JOB",
                canonical_title="Synthetic target",
                issuer_name="Test",
                jurisdiction=None,
                current_version=None,
                status="DRAFT",
                publication_status="INTERNAL",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            OpportunityVersion(
                opportunity_id=identity,
                version=1,
                effective_from=NOW,
                source_document_id=doc.document_id,
                source_evidence_ref_id=ref.evidence_ref_id,
                snapshot={},
                field_evidence=[],
                changes=[{"synthetic": True}],
                content_sha256="a" * 64,
                review_status="PENDING",
                created_at=NOW,
            )
        )
        session.flush()
        opportunity = session.get(Opportunity, identity)
        assert opportunity is not None
        opportunity.current_version = 1
    return identity


def _command(delivery: ValidatedDelivery, identity: UUID, **overrides: object) -> BindInvestigation:
    return BindInvestigation.model_validate(
        {
            "delivery_hash": delivery.sha256,
            "opportunity_id": str(identity),
            "opportunity_version": 1,
            "positions": [],
            "reason": "Synthetic identity association only.",
            **overrides,
        }
    )


def test_binding_freezes_real_wma_lineage_without_acquisition_or_fact_rows(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    result = h.store.bind(task_id, _command(delivery, identity), h.principal, "binding-one")
    binding = result["entity_binding"]
    assert binding["scope"] == "ENTITY_ASSOCIATION_ONLY"
    assert binding["unmapped_position_ids"] == ["position"]
    with h.factory() as session:
        member = session.scalar(select(SourceBundleMember))
        assert member is not None
        assert member.provenance_kind == "DIRECT_WMA"
        assert member.wma_task_id == task_id
        assert member.wma_delivery_hash == delivery.sha256
        assert member.acquisition_run_id is None
        assert member.capture_observation_id is None
        expected = session.scalar(
            text("select p9b_expected_member_hash(:id)"), {"id": member.source_bundle_member_id}
        )
        assert expected == member.member_provenance_hash
        revision = session.get(SourceBundleRevision, UUID(binding["source_bundle_revision_id"]))
        assert revision is not None
        assert revision.status == "FROZEN"
        for model in (AcquisitionRun, AcquisitionEvaluation, CaptureObservation, VerifiedFact):
            assert _count(session, model) == 0
        opportunity = session.get(Opportunity, identity)
        assert opportunity is not None and opportunity.publication_status == "INTERNAL"
    assert (
        h.store.bind(task_id, _command(delivery, identity), h.principal, "binding-one")[
            "entity_binding"
        ]
        == binding
    )
    with pytest.raises(InvestigationError, match="BINDING_IDEMPOTENCY_CONFLICT"):
        h.store.bind(
            task_id, _command(delivery, identity, reason="Changed"), h.principal, "binding-one"
        )


def test_binding_requires_intake_approval_and_exact_delivery(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h, approved=False)
    with pytest.raises(InvestigationError, match="BINDING_DELIVERY_CONFLICT"):
        h.store.bind(task_id, _command(delivery, identity), h.principal, "binding-one")
    h.store.review(task_id, _review(delivery), h.principal, "synthetic-review")
    with pytest.raises(InvestigationError, match="BINDING_DELIVERY_CONFLICT"):
        h.store.bind(
            task_id,
            _command(delivery, identity, delivery_hash="0" * 64),
            h.principal,
            "binding-one",
        )


def test_sql_cannot_disguise_missing_acquisition_as_wma(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    h.store.bind(task_id, _command(delivery, identity), h.principal, "binding-one")
    with h.factory() as session:
        member = session.scalar(select(SourceBundleMember))
        assert member is not None
        member_id = member.source_bundle_member_id
    with pytest.raises(DBAPIError), h.factory.begin() as session:
        session.execute(
            text(
                "update source_bundle_members set wma_delivery_hash = :hash "
                "where source_bundle_member_id = :id"
            ),
            {"id": member_id, "hash": "0" * 64},
        )
    with pytest.raises(DBAPIError), h.factory.begin() as session:
        session.execute(
            text("delete from investigation_bindings where task_id = :id"), {"id": task_id}
        )


def test_position_binding_requires_exact_identity_and_keeps_previous_snapshot(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    first = h.store.bind(task_id, _command(delivery, identity), h.principal, "first")[
        "entity_binding"
    ]
    with h.factory.begin() as session:
        unit = OpportunityUnitService(session).create_unit(
            opportunity_id=identity,
            opportunity_version=1,
            source_bundle_revision_id=UUID(first["source_bundle_revision_id"]),
            seed=UnitSeed("P1", "POSITION", "Synthetic position", "b" * 64),
            effective_from=NOW,
        )
        unit_id, version_id = unit.opportunity_unit_id, unit.current_version_id
    position = {
        "entity_id": "position",
        "opportunity_unit_id": str(unit_id),
        "opportunity_unit_version_id": str(version_id),
    }
    second_command = _command(
        delivery, identity, positions=[position], previous_binding_id=first["binding_id"]
    )
    second = h.store.bind(task_id, second_command, h.principal, "second")["entity_binding"]
    assert second["sequence"] == 2 and second["unmapped_position_ids"] == []
    assert second["positions"] == [position]
    replay = h.store.bind(task_id, _command(delivery, identity), h.principal, "first")
    assert replay["binding_receipt"] == first
    assert replay["entity_binding"] == second
    with pytest.raises(InvestigationError, match="BINDING_REVISION_CONFLICT"):
        h.store.bind(task_id, second_command, h.principal, "stale")
    for invalid in (
        position | {"entity_id": "unit"},
        position | {"opportunity_unit_version_id": str(uuid7())},
    ):
        with pytest.raises(InvestigationError, match="BINDING_POSITION_VERSION_CONFLICT"):
            h.store.bind(
                task_id,
                _command(
                    delivery,
                    identity,
                    positions=[invalid],
                    previous_binding_id=second["binding_id"],
                ),
                h.principal,
                "invalid",
            )
    with pytest.raises(InvestigationError, match="BINDING_POSITION_DUPLICATE"):
        h.store.bind(
            task_id,
            _command(
                delivery,
                identity,
                positions=[position, position],
                previous_binding_id=second["binding_id"],
            ),
            h.principal,
            "duplicate",
        )


def test_binding_rechecks_actual_reviewer_and_does_not_trust_claimed_flags(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    with h.factory.begin() as session:
        reviewer = session.get(ReviewerAccountModel, h.principal.reviewer_id)
        assert reviewer is not None
        reviewer.synthetic = True
    with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        h.store.bind(
            task_id, _command(delivery, identity), replace(h.principal, synthetic=False), "rejected"
        )
    with h.factory() as session:
        assert _count(session, SourceBundleRevision) == 0


@pytest.mark.parametrize("derived", [False, True])
def test_missing_original_or_derived_text_rolls_back_binding(
    harness: StoreHarness, derived: bool
) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    from urllib.parse import urlsplit

    from deepaha.artifacts.models import RawArtifact

    with h.factory() as session:
        document = session.scalar(select(Document))
        assert document is not None and document.extracted_text_uri is not None
        raw = session.get(RawArtifact, document.artifact_id)
        assert raw is not None
        key = urlsplit(document.extracted_text_uri).path.lstrip("/") if derived else raw.object_key
    metadata = h.objects.stat(key=key)
    h.objects.delete_if_matches(key=key, sha256=metadata.sha256)
    with pytest.raises(InvestigationError, match="STORED_.*_INTEGRITY_FAILED"):
        h.store.bind(task_id, _command(delivery, identity), h.principal, "missing-bytes")
    with h.factory() as session:
        assert _count(session, SourceBundleRevision) == 0


def test_concurrent_duplicate_associations_create_one_frozen_bundle(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: h.store.bind(task_id, _command(delivery, identity), h.principal, "same"),
                range(2),
            )
        )
    assert results[0]["binding_receipt"] == results[1]["binding_receipt"]
    with h.factory() as session:
        assert _count(session, SourceBundleRevision) == 1


def test_distinct_material_urls_with_identical_bytes_keep_all_wma_lineage(
    harness: StoreHarness,
) -> None:
    from deepaha.investigations.contracts import BindInvestigation, ReviewInvestigation
    from tests.integration.test_investigation_documents import _with_extras

    h = harness
    content = b"<html><body><p>Shared attachment content</p></body></html>"
    task_id, delivery_hash = _with_extras(
        h,
        {
            "attachment-a.html": ("text/html", content),
            "attachment-b.html": ("text/html", content),
        },
    )
    h.store.prepare_documents(task_id, delivery_hash, h.principal)
    h.store.review(
        task_id,
        ReviewInvestigation(
            decision="APPROVE", delivery_hash=delivery_hash, reason="Synthetic intake approval"
        ),
        h.principal,
        "approve",
    )
    result = h.store.bind(
        task_id,
        BindInvestigation(
            delivery_hash=delivery_hash,
            opportunity_id=_target(h),
            opportunity_version=1,
            reason="相同字节但来源材料不同的合成测试",
        ),
        h.principal,
        "bind",
    )
    with h.factory() as session:
        members = list(session.scalars(select(SourceBundleMember)))
        assert len(members) == 3
        assert len({member.document_id for member in members}) == 2
        assert {member.wma_material_id for member in members} == {
            "notice",
            "attachment-a.html",
            "attachment-b.html",
        }
    assert result["entity_binding"]["bundle_status"] == "FROZEN"


def test_uppercase_manifest_digest_preserves_original_and_binds(harness: StoreHarness) -> None:
    import json

    from deepaha.investigations.delivery import validate_delivery
    from deepaha.investigations.models import InvestigationTask
    from tests.integration.test_investigation_store import _collecting, _files

    h = harness
    task_id, owner = _collecting(h)
    files, artifacts = _files(task_id)
    evidence = json.loads(files["evidence.json"])
    original_hash = evidence["artifacts"][0]["sha256"].upper()
    evidence["artifacts"][0]["sha256"] = original_hash
    files["evidence.json"] = json.dumps(evidence).encode()
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task_id, owner, files)
    h.store.finish(task_id, owner, delivery, files)
    h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    h.store.review(task_id, _review(delivery), h.principal, "approve")
    result = h.store.bind(task_id, _command(delivery, _target(h)), h.principal, "bind")
    assert result["entity_binding"]["bundle_status"] == "FROZEN"
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and isinstance(task.delivery, dict)
        stored_evidence = task.delivery["evidence"]
        assert isinstance(stored_evidence, dict)
        artifacts = stored_evidence["artifacts"]
        assert isinstance(artifacts, list) and isinstance(artifacts[0], dict)
        assert artifacts[0]["sha256"] == original_hash


def test_unsupported_material_prevents_partial_bundle(harness: StoreHarness) -> None:
    from deepaha.investigations.contracts import BindInvestigation, ReviewInvestigation
    from tests.integration.test_investigation_documents import _with_extras

    h = harness
    task_id, delivery_hash = _with_extras(
        h, {"legacy.doc": ("application/msword", b"Unsupported synthetic content")}
    )
    h.store.prepare_documents(task_id, delivery_hash, h.principal)
    h.store.review(
        task_id,
        ReviewInvestigation(
            decision="APPROVE", delivery_hash=delivery_hash, reason="Synthetic intake approval"
        ),
        h.principal,
        "approve",
    )
    command = BindInvestigation(
        delivery_hash=delivery_hash,
        opportunity_id=_target(h),
        opportunity_version=1,
        reason="Synthetic association",
    )
    with pytest.raises(InvestigationError, match="BINDING_DOCUMENTS_NOT_READY"):
        h.store.bind(task_id, command, h.principal, "partial")
    with h.factory() as session:
        assert _count(session, SourceBundleRevision) == 0


@pytest.mark.parametrize("approved", [False, True])
def test_frozen_delivery_rejects_late_material_insertion(
    harness: StoreHarness, approved: bool
) -> None:
    from deepaha.investigations.models import InvestigationMaterial

    h = harness
    task_id, _, _ = _prepared(h, approved=approved)
    with h.factory() as session:
        original = session.scalar(select(InvestigationMaterial))
        assert original is not None
        raw_id, metadata = original.raw_artifact_id, original.metadata_snapshot
    with (
        pytest.raises(DBAPIError, match="INVESTIGATION_MATERIAL_SET_FROZEN"),
        h.factory.begin() as session,
    ):
        session.add(
            InvestigationMaterial(
                task_id=task_id,
                material_id="late",
                raw_artifact_id=raw_id,
                metadata_snapshot=metadata | {"artifact_id": "late"},
            )
        )
        session.flush()


def test_downgrade_preserves_wma_binding_history(harness: StoreHarness) -> None:
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    h = harness
    task_id, delivery, identity = _prepared(h)
    binding = h.store.bind(task_id, _command(delivery, identity), h.principal, "one")[
        "entity_binding"
    ]
    # Exercise this historical guard directly: newer receipt/anchor migrations
    # now correctly reject the end-to-end downgrade before reaching 0037.
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20260907_0037")
    assert revision is not None
    with (
        h.factory.begin() as session,
        Operations.context(MigrationContext.configure(session.connection())),
        pytest.raises(RuntimeError, match="Cannot remove WMA provenance"),
    ):
        revision.module.downgrade()
    assert h.store.get(task_id)["entity_binding"] == binding
    with h.factory() as session:
        assert (
            session.scalar(text("select version_num from alembic_version"))
            == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        )


@pytest.mark.parametrize(
    "change",
    [
        {"wma_delivery_hash": "0" * 64},
        {"wma_contract_hash": "0" * 64},
        {"wma_material_id": "nonexistent"},
        {"source_id": uuid7()},
        {"parse_attempt_id": uuid7()},
        {"provenance_kind": "ACQUISITION"},
        {"capture_observation_id": uuid7()},
    ],
)
def test_direct_sql_insertion_rejects_forged_wma_provenance(
    harness: StoreHarness, change: dict[str, str | UUID]
) -> None:
    h = harness
    task_id, delivery, identity = _prepared(h)
    h.store.bind(task_id, _command(delivery, identity), h.principal, "one")
    with h.factory() as session:
        original = session.scalar(select(SourceBundleMember))
        assert original is not None
        revision = session.get(SourceBundleRevision, original.source_bundle_revision_id)
        assert revision is not None
        revision_values = {c.name: getattr(revision, c.name) for c in revision.__table__.columns}
        member_values = {c.name: getattr(original, c.name) for c in original.__table__.columns}
    with pytest.raises(DBAPIError), h.factory.begin() as session:
        draft = SourceBundleRevision(
            **(
                revision_values
                | {
                    "source_bundle_revision_id": uuid7(),
                    "revision_number": 2,
                    "status": "DRAFT",
                    "frozen_at": None,
                    "canonical_bundle_hash": "0" * 64,
                }
            )
        )
        session.add(draft)
        session.flush()
        session.add(
            SourceBundleMember(
                **(
                    member_values
                    | {
                        "source_bundle_member_id": uuid7(),
                        "source_bundle_revision_id": draft.source_bundle_revision_id,
                    }
                    | change
                )
            )
        )
        session.flush()
