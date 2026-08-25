from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Event, Thread
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase9b import (
    AnswerAccessClass,
    DatasetManifestEntrySchemaV08,
    DatasetManifestSchemaV08,
    DatasetPartition,
)
from deepaha.documents.models import Document, EvidenceRef
from deepaha.documents.parser import LEGACY_PARSE_CONTRACT_VERSION
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.datasets import (
    DatasetLeakageError,
    DatasetManifestRepository,
    build_frozen_manifest,
)
from deepaha.p9b.hashing import document_parse_key
from deepaha.p9b.identity import (
    OpportunityUnitService,
    UnitConcurrencyConflict,
    UnitIdentityCollision,
    UnitIdentityError,
    UnitSeed,
)
from deepaha.p9b.models import (
    DatasetManifest,
    DatasetManifestEntry,
    OpportunityUnitAlias,
    OpportunityUnitLineageEvent,
    OpportunityUnitVersion,
    SourceBundleMember,
    SourceBundleMemberRelation,
    SourceBundleRevision,
)
from deepaha.p9b.provenance import (
    BundleMemberSpec,
    BundleProvenanceError,
    BundleService,
)
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
CONTENT = b"synthetic P9-B official notice"
CONTENT_HASH = sha256(CONTENT).hexdigest()


@dataclass(frozen=True)
class Graph:
    opportunity_id: UUID
    opportunity_version: int
    document_id: UUID
    observation_id: UUID
    evaluation_id: UUID
    run_id: UUID
    evidence_ref_id: UUID


def seed_graph(session: Session, *, suffix: str = "one") -> Graph:
    source_id = uuid7()
    endpoint_id = uuid7()
    artifact_id = uuid7()
    document_id = uuid7()
    observation_id = uuid7()
    evaluation_id = uuid7()
    run_id = uuid7()
    recipe_id = uuid7()
    evidence_ref_id = uuid7()
    opportunity_id = uuid7()
    url = f"https://p9b-{suffix}.example.gov/notices/1"
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://p9b-{suffix}.example.gov/",
        authority_name="Synthetic P9-B Authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction=None,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    endpoint = SourceEndpoint(
        endpoint_id=endpoint_id,
        source_id=source_id,
        url=url,
        allowed_hosts=[f"p9b-{suffix}.example.gov"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=21_600,
        timeout_seconds=30,
        max_attempts=2,
        robots_url=f"https://p9b-{suffix}.example.gov/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=NOW,
        content_use_basis="LINK_ONLY",
        license_name=None,
        license_url=None,
        attribution="Synthetic P9-B Authority",
        fixture_storage_allowed=False,
        usage_note="Synthetic P9-B persistence test only.",
        policy_version="2026-08-24.1",
        active=True,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    artifact = RawArtifact(
        artifact_id=artifact_id,
        source_id=source_id,
        requested_url=url,
        resolved_url=url,
        retrieved_at=NOW,
        http_status=200,
        media_type="text/html",
        content_sha256=CONTENT_HASH,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{CONTENT_HASH[:2]}/{CONTENT_HASH}",
        byte_size=len(CONTENT),
        collector_version="1.0.0",
        metadata_schema_version="0.2.0",
    )
    observation = CaptureObservation(
        observation_id=observation_id,
        collection_run_id=uuid7(),
        attempt_number=1,
        endpoint_id=endpoint_id,
        source_id=source_id,
        requested_url=url,
        resolved_url=url,
        started_at=NOW,
        completed_at=NOW,
        outcome="SUCCEEDED",
        http_status=200,
        response_etag=None,
        response_last_modified=None,
        artifact_id=artifact_id,
        error_code=None,
        collector_name="static-http",
        collector_version="1.0.0",
        policy_version=endpoint.policy_version,
    )
    evaluation = AcquisitionEvaluation(
        acquisition_evaluation_id=evaluation_id,
        observation_id=observation_id,
        endpoint_id=endpoint_id,
        source_id=source_id,
        artifact_id=artifact_id,
        strategy_used="STATIC_HTTP",
        validation_status="VALID",
        challenge_type=None,
        redirect_chain=[url],
        discovered_count=1,
        manual_intervention=False,
        diagnostic_codes=[],
        validator_name="deepaha-content-validator",
        validator_version="1.0.0",
        metrics_schema_version="1.0.0",
        validation_metrics={"byte_size": len(CONTENT)},
        evaluated_at=NOW,
        contract_version="1.0.0",
    )
    run = AcquisitionRun(
        acquisition_run_id=run_id,
        recipe_id=recipe_id,
        source_id=source_id,
        endpoint_id=endpoint_id,
        endpoint_policy_version=endpoint.policy_version,
        recipe_version="2026-08-24.1",
        started_at=NOW,
        completed_at=NOW,
        terminal_code="COMPLETE",
        request_count=1,
        strategy_attempts=[
            {
                "strategy": "STATIC_HTTP",
                "validation_status": "VALID",
                "error_code": None,
                "capture_observation_id": str(observation_id),
                "acquisition_evaluation_id": str(evaluation_id),
                "raw_artifact_id": str(artifact_id),
            }
        ],
        discovered_count=1,
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
    parse_key = document_parse_key(
        artifact_id=artifact_id,
        artifact_sha256=CONTENT_HASH,
        parser_name="deepaha-html",
        parser_version="1.0.0",
        parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
    )
    document = Document(
        document_id=document_id,
        artifact_id=artifact_id,
        title="Synthetic P9-B notice",
        published_at=NOW,
        language="zh-CN",
        extracted_text_uri=None,
        parser_name="deepaha-html",
        parser_version="1.0.0",
        parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        document_parse_key=parse_key,
        parse_confidence=None,
        created_at=NOW,
    )
    evidence = EvidenceRef(
        evidence_ref_id=evidence_ref_id,
        document_id=document_id,
        artifact_id=artifact_id,
        locator_kind="full_document",
        locator_value="*",
        locator_schema_version="0.1.0",
        locator_payload=None,
        quote_sha256=CONTENT_HASH,
    )
    opportunity = Opportunity(
        opportunity_id=opportunity_id,
        public_id=f"opp_{opportunity_id.hex}",
        type="YOUTH_DEVELOPMENT_PROGRAM",
        canonical_title="Synthetic P9-B opportunity",
        issuer_name="Synthetic P9-B Authority",
        jurisdiction=None,
        current_version=None,
        status="OPEN",
        publication_status="INTERNAL",
        created_at=NOW,
        updated_at=NOW,
    )
    version = OpportunityVersion(
        opportunity_id=opportunity_id,
        version=1,
        effective_from=NOW,
        source_document_id=document_id,
        source_evidence_ref_id=evidence_ref_id,
        snapshot={
            "canonical_title": opportunity.canonical_title,
            "type": opportunity.type,
            "issuer_name": opportunity.issuer_name,
            "jurisdiction": None,
            "status": opportunity.status,
            "published_at": NOW.isoformat(),
            "application_window": {"opens_on": None, "closes_on": None, "timezone": None},
            "application_url": None,
            "attachment_urls": [],
            "locations": [],
        },
        field_evidence=[
            {
                "field_path": "canonical_title",
                "precedence": 600,
                "evidence_ref_id": str(evidence_ref_id),
                "effective_at": NOW.isoformat(),
            }
        ],
        changes=[
            {
                "field_path": "canonical_title",
                "before": None,
                "after": opportunity.canonical_title,
                "evidence_ref_id": str(evidence_ref_id),
            }
        ],
        content_sha256=CONTENT_HASH,
        review_status="NOT_REQUIRED",
        created_at=NOW,
    )
    session.add(source)
    session.flush()
    session.add_all([endpoint, artifact, opportunity])
    session.flush()
    session.add_all([observation, run, document])
    session.flush()
    session.add_all([evaluation, evidence])
    session.flush()
    session.add(version)
    session.flush()
    opportunity.current_version = 1
    session.flush()
    return Graph(
        opportunity_id=opportunity_id,
        opportunity_version=1,
        document_id=document_id,
        observation_id=observation_id,
        evaluation_id=evaluation_id,
        run_id=run_id,
        evidence_ref_id=evidence_ref_id,
    )


def member_spec(graph: Graph) -> BundleMemberSpec:
    return BundleMemberSpec(
        document_id=graph.document_id,
        capture_observation_id=graph.observation_id,
        acquisition_evaluation_id=graph.evaluation_id,
        acquisition_run_id=graph.run_id,
        member_role="PRIMARY_NOTICE",
        precedence=1000,
        effective_from=NOW,
        effective_to=None,
    )


def frozen_bundle(session: Session, graph: Graph) -> SourceBundleRevision:
    service = BundleService(session)
    revision = service.create_revision(
        opportunity_id=graph.opportunity_id,
        opportunity_version=graph.opportunity_version,
        effective_as_of=NOW,
        members=[member_spec(graph)],
    )
    return service.freeze_revision(revision.source_bundle_revision_id, frozen_at=NOW)


def calibration_manifest(
    session: Session,
    graph: Graph,
    revision: SourceBundleRevision,
) -> DatasetManifestSchemaV08:
    unit_service = OpportunityUnitService(session)
    entries = []
    for index in range(30):
        unit = unit_service.create_unit(
            opportunity_id=graph.opportunity_id,
            opportunity_version=graph.opportunity_version,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            seed=UnitSeed(
                f"POSITION-{index:03d}",
                "POSITION",
                f"Position {index:03d}",
                f"{index + 1:064x}",
            ),
            effective_from=NOW,
        )
        assert unit.current_version_id is not None
        entries.append(
            DatasetManifestEntrySchemaV08(
                entry_id=f"calibration-{index:03d}",
                partition=DatasetPartition.CALIBRATION,
                opportunity_id=graph.opportunity_id,
                opportunity_version=graph.opportunity_version,
                opportunity_unit_id=unit.opportunity_unit_id,
                opportunity_unit_version_id=unit.current_version_id,
                source_bundle_id=revision.source_bundle_id,
                source_bundle_revision_id=revision.source_bundle_revision_id,
                canonical_bundle_hash=revision.canonical_bundle_hash,
                atomic_group_id="bundle-calibration-001",
                near_duplicate_cluster_ids=["notice-family-calibration-001"],
                unit_lineage_ids=[],
                evaluation_as_of=NOW,
                answer_access_class=AnswerAccessClass.ASSISTED_CALIBRATION,
            )
        )
    return build_frozen_manifest(
        partition=DatasetPartition.CALIBRATION,
        entries=entries,
        evaluation_cutoff=NOW,
        frozen_by="synthetic-human-curator",
        frozen_at=NOW,
    )


def test_bundle_freeze_materializes_member_level_provenance_and_is_immutable(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        graph = seed_graph(session)
        revision = frozen_bundle(session, graph)
        revision_id = revision.source_bundle_revision_id
        bundle_hash = revision.canonical_bundle_hash
        document_id = graph.document_id
        session.commit()

    with Session(migrated_engine) as verification:
        member = verification.scalar(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == revision_id
            )
        )
        assert member is not None
        assert bundle_hash != "0" * 64
        assert member.acquisition_validation_status == "VALID"
        assert member.raw_artifact_sha256 == CONTENT_HASH
        assert member.document_id == document_id
        assert len(member.member_provenance_hash) == 64

    with (
        pytest.raises(DBAPIError, match="cannot be deleted"),
        migrated_engine.begin() as connection,
    ):
        connection.execute(
            text(
                "delete from source_bundle_revisions where source_bundle_revision_id = :revision_id"
            ),
            {"revision_id": revision_id},
        )


def test_bundle_creation_rejects_cross_bound_run_before_persistence(session: Session) -> None:
    first = seed_graph(session, suffix="first")
    second = seed_graph(session, suffix="second")

    with pytest.raises(BundleProvenanceError, match="AcquisitionRun"):
        BundleService(session).create_revision(
            opportunity_id=first.opportunity_id,
            opportunity_version=first.opportunity_version,
            effective_as_of=NOW,
            members=[replace(member_spec(first), acquisition_run_id=second.run_id)],
        )


def test_bundle_creation_rejects_same_endpoint_run_without_exact_observation_lineage(
    session: Session,
) -> None:
    graph = seed_graph(session, suffix="same-endpoint")
    original = session.get(AcquisitionRun, graph.run_id)
    assert original is not None
    unrelated_run_id = uuid7()
    session.add(
        AcquisitionRun(
            acquisition_run_id=unrelated_run_id,
            recipe_id=uuid7(),
            source_id=original.source_id,
            endpoint_id=original.endpoint_id,
            endpoint_policy_version=original.endpoint_policy_version,
            recipe_version="2026-08-24.unrelated",
            started_at=NOW,
            completed_at=NOW,
            terminal_code="COMPLETE",
            request_count=1,
            strategy_attempts=[
                {
                    "strategy": "STATIC_HTTP",
                    "validation_status": "VALID",
                    "error_code": None,
                    "capture_observation_id": str(uuid7()),
                    "acquisition_evaluation_id": str(uuid7()),
                    "raw_artifact_id": str(uuid7()),
                }
            ],
            discovered_count=1,
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
    )
    session.flush()

    with pytest.raises(BundleProvenanceError, match="exact Observation lineage"):
        BundleService(session).create_revision(
            opportunity_id=graph.opportunity_id,
            opportunity_version=graph.opportunity_version,
            effective_as_of=NOW,
            members=[replace(member_spec(graph), acquisition_run_id=unrelated_run_id)],
        )


def test_database_rejects_forged_direct_revision_freeze(session: Session) -> None:
    graph = seed_graph(session, suffix="direct-freeze")
    revision = BundleService(session).create_revision(
        opportunity_id=graph.opportunity_id,
        opportunity_version=graph.opportunity_version,
        effective_as_of=NOW,
        members=[member_spec(graph)],
    )
    session.flush()

    with pytest.raises(DBAPIError, match="P9B_BUNDLE_FREEZE_PROOF_MISMATCH"):
        session.execute(
            text(
                "update source_bundle_revisions "
                "set canonical_bundle_hash = :forged_hash, status = 'FROZEN', frozen_at = :now "
                "where source_bundle_revision_id = :revision_id"
            ),
            {
                "forged_hash": "f" * 64,
                "now": NOW,
                "revision_id": revision.source_bundle_revision_id,
            },
        )


@pytest.mark.parametrize("initial_status", ["FROZEN", "INVALIDATED"])
def test_database_rejects_direct_non_draft_revision_insert_without_provenance(
    session: Session,
    initial_status: str,
) -> None:
    graph = seed_graph(session, suffix=f"direct-{initial_status.lower()}-insert")
    draft = BundleService(session).create_revision(
        opportunity_id=graph.opportunity_id,
        opportunity_version=graph.opportunity_version,
        effective_as_of=NOW,
        members=[member_spec(graph)],
    )
    session.flush()

    with pytest.raises(DBAPIError, match="P9B_BUNDLE_INITIAL_STATE_MISMATCH"):
        session.execute(
            text(
                "insert into source_bundle_revisions "
                "(source_bundle_revision_id, source_bundle_id, opportunity_id, "
                "opportunity_version, revision_number, canonical_bundle_hash, "
                "relation_graph_version, precedence_graph_version, effective_as_of, "
                "status, created_at, frozen_at) values "
                "(:revision_id, :bundle_id, :opportunity_id, :opportunity_version, 2, "
                ":forged_hash, 'p9b-relation-graph-v1', 'p9b-precedence-graph-v1', :now, "
                ":status, :now, :now)"
            ),
            {
                "revision_id": uuid7(),
                "bundle_id": draft.source_bundle_id,
                "opportunity_id": graph.opportunity_id,
                "opportunity_version": graph.opportunity_version,
                "forged_hash": "f" * 64,
                "status": initial_status,
                "now": NOW,
            },
        )


def test_member_relation_insert_and_revision_freeze_serialize_on_parent_row(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as setup:
        primary = seed_graph(setup, suffix="freeze-lock-primary")
        attachment = seed_graph(setup, suffix="freeze-lock-attachment")
        revision = BundleService(setup).create_revision(
            opportunity_id=primary.opportunity_id,
            opportunity_version=primary.opportunity_version,
            effective_as_of=NOW,
            members=[
                member_spec(primary),
                replace(member_spec(attachment), member_role="ATTACHMENT", precedence=500),
            ],
        )
        revision_id = revision.source_bundle_revision_id
        member_ids = tuple(
            setup.scalars(
                select(SourceBundleMember.source_bundle_member_id)
                .where(SourceBundleMember.source_bundle_revision_id == revision_id)
                .order_by(SourceBundleMember.source_bundle_member_id)
            )
        )
        setup.commit()

    insert_connection = migrated_engine.connect()
    insert_transaction = insert_connection.begin()
    started = Event()
    outcome: dict[str, object] = {}
    try:
        insert_connection.execute(
            text(
                "insert into source_bundle_member_relations "
                "(source_bundle_revision_id, source_member_id, target_member_id, "
                "relation_type, created_at) values "
                "(:revision_id, :source_id, :target_id, 'ATTACHES_TO', :created_at)"
            ),
            {
                "revision_id": revision_id,
                "source_id": member_ids[1],
                "target_id": member_ids[0],
                "created_at": NOW,
            },
        )

        def freeze_in_second_transaction() -> None:
            with Session(migrated_engine) as freezer:
                started.set()
                try:
                    BundleService(freezer).freeze_revision(revision_id, frozen_at=NOW)
                    freezer.commit()
                    outcome["status"] = "COMMITTED"
                except Exception as error:  # noqa: BLE001 - assertion captures DB outcome
                    freezer.rollback()
                    outcome["error"] = error

        thread = Thread(target=freeze_in_second_transaction, daemon=True)
        thread.start()
        assert started.wait(timeout=2)
        thread.join(timeout=0.25)
        assert thread.is_alive(), "freeze did not wait for the in-flight member graph mutation"
        insert_transaction.commit()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert isinstance(outcome.get("error"), DBAPIError)
        assert "P9B_BUNDLE_FREEZE_PROOF_MISMATCH" in str(outcome["error"])
    finally:
        if insert_transaction.is_active:
            insert_transaction.rollback()
        insert_connection.close()

    with Session(migrated_engine) as verification:
        persisted = verification.get(SourceBundleRevision, revision_id)
        assert persisted is not None
        assert persisted.status == "DRAFT"


def test_multi_member_bundle_keeps_each_attachment_provenance_and_relation(
    session: Session,
) -> None:
    primary = seed_graph(session, suffix="primary")
    attachment = seed_graph(session, suffix="attachment")
    service = BundleService(session)
    revision = service.create_revision(
        opportunity_id=primary.opportunity_id,
        opportunity_version=primary.opportunity_version,
        effective_as_of=NOW,
        members=[
            member_spec(primary),
            replace(
                member_spec(attachment),
                member_role="ATTACHMENT",
                precedence=500,
                relation_type="ATTACHES_TO",
                related_member_index=0,
            ),
        ],
    )
    service.freeze_revision(revision.source_bundle_revision_id, frozen_at=NOW)

    members = tuple(
        session.scalars(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == revision.source_bundle_revision_id
            )
        )
    )
    relation = session.scalar(
        select(SourceBundleMemberRelation).where(
            SourceBundleMemberRelation.source_bundle_revision_id
            == revision.source_bundle_revision_id
        )
    )
    assert len(members) == 2
    assert {member.document_id for member in members} == {
        primary.document_id,
        attachment.document_id,
    }
    assert relation is not None
    assert relation.relation_type == "ATTACHES_TO"


def test_dataset_manifest_persists_exact_counts_hash_and_invalidation_audit(
    session: Session,
) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    manifest = calibration_manifest(session, graph, revision)
    repository = DatasetManifestRepository(session)

    row = repository.persist_frozen(manifest)

    assert row.status == "FROZEN"
    assert row.expected_entry_count == row.actual_entry_count == 30
    assert row.atomic_group_count == 1
    assert row.manifest_hash == manifest.manifest_hash
    assert (
        session.scalar(
            select(func.count())
            .select_from(DatasetManifestEntry)
            .where(DatasetManifestEntry.dataset_manifest_id == row.dataset_manifest_id)
        )
        == 30
    )

    invalidated = repository.invalidate(
        manifest.manifest_hash,
        invalidated_at=NOW + timedelta(days=1),
        reason="Synthetic successor replaces this frozen manifest",
        successor_manifest_hash="f" * 64,
    )
    assert invalidated.status == "INVALIDATED"
    assert invalidated.successor_manifest_hash == "f" * 64
    with pytest.raises(DatasetLeakageError, match="invalidated"):
        repository.persist_frozen(manifest)


def test_database_rejects_persistent_cross_partition_leakage(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    manifest = calibration_manifest(session, graph, revision)
    frozen = DatasetManifestRepository(session).persist_frozen(manifest)
    original = session.scalar(
        select(DatasetManifestEntry).where(
            DatasetManifestEntry.dataset_manifest_id == frozen.dataset_manifest_id
        )
    )
    assert original is not None
    draft_id = uuid7()
    session.add(
        DatasetManifest(
            dataset_manifest_id=draft_id,
            split_manifest_version="p9b-split-manifest-v0.8.0",
            partition="DEVELOPMENT",
            expected_entry_count=70,
            actual_entry_count=0,
            atomic_group_count=0,
            evaluation_cutoff=NOW,
            answer_access_class="DEVELOPMENT_VISIBLE",
            status="DRAFT",
            frozen_by="synthetic-human-curator",
            created_at=NOW,
            frozen_at=None,
            invalidated_at=None,
            invalidation_reason=None,
            successor_manifest_hash=None,
            manifest_hash="e" * 64,
        )
    )
    session.flush()
    session.add(
        DatasetManifestEntry(
            dataset_manifest_id=draft_id,
            entry_id="development-leak",
            partition="DEVELOPMENT",
            opportunity_id=original.opportunity_id,
            opportunity_version=original.opportunity_version,
            opportunity_unit_id=original.opportunity_unit_id,
            opportunity_unit_version_id=original.opportunity_unit_version_id,
            source_bundle_id=original.source_bundle_id,
            source_bundle_revision_id=original.source_bundle_revision_id,
            canonical_bundle_hash=original.canonical_bundle_hash,
            atomic_group_id=original.atomic_group_id,
            near_duplicate_cluster_ids=original.near_duplicate_cluster_ids,
            unit_lineage_ids=original.unit_lineage_ids,
            evaluation_as_of=NOW,
            answer_access_class="DEVELOPMENT_VISIBLE",
            created_at=NOW,
        )
    )

    with pytest.raises(DBAPIError, match="DATASET_PARTITION_LEAKAGE"):
        session.flush()


def test_unit_version_append_uses_compare_and_swap(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    unit = service.create_default_singleton(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW,
        canonical_label="Default singleton",
        identity_fingerprint="1" * 64,
    )
    first_pointer = unit.current_version_id

    second = service.append_version_cas(
        opportunity_unit_id=unit.opportunity_unit_id,
        expected_current_version_id=first_pointer,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW + timedelta(minutes=1),
        canonical_label="Renamed singleton",
        identity_fingerprint="2" * 64,
    )
    assert unit.current_version_id == second.opportunity_unit_version_id

    with pytest.raises(UnitConcurrencyConflict):
        service.append_version_cas(
            opportunity_unit_id=unit.opportunity_unit_id,
            expected_current_version_id=first_pointer,
            opportunity_version=1,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            effective_from=NOW + timedelta(minutes=2),
            canonical_label="Stale writer",
            identity_fingerprint="3" * 64,
        )
    assert (
        session.scalar(
            select(func.count())
            .select_from(OpportunityUnitVersion)
            .where(OpportunityUnitVersion.opportunity_unit_id == unit.opportunity_unit_id)
        )
        == 2
    )


def test_unit_current_pointer_and_parent_version_advance_atomically(session: Session) -> None:
    graph = seed_graph(session, suffix="unit-parent-version")
    first_revision = frozen_bundle(session, graph)
    opportunity = session.get(Opportunity, graph.opportunity_id)
    assert opportunity is not None
    session.add(
        OpportunityVersion(
            opportunity_id=graph.opportunity_id,
            version=2,
            effective_from=NOW + timedelta(minutes=1),
            source_document_id=graph.document_id,
            source_evidence_ref_id=graph.evidence_ref_id,
            snapshot={"canonical_title": opportunity.canonical_title},
            field_evidence=[
                {
                    "field_path": "canonical_title",
                    "precedence": 600,
                    "evidence_ref_id": str(graph.evidence_ref_id),
                    "effective_at": (NOW + timedelta(minutes=1)).isoformat(),
                }
            ],
            changes=[
                {
                    "field_path": "canonical_title",
                    "before": opportunity.canonical_title,
                    "after": opportunity.canonical_title,
                    "evidence_ref_id": str(graph.evidence_ref_id),
                }
            ],
            content_sha256="8" * 64,
            review_status="NOT_REQUIRED",
            created_at=NOW + timedelta(minutes=1),
        )
    )
    session.flush()
    opportunity.current_version = 2
    session.flush()
    second_revision = BundleService(session).create_revision(
        opportunity_id=graph.opportunity_id,
        opportunity_version=2,
        effective_as_of=NOW + timedelta(minutes=1),
        members=[member_spec(graph)],
    )
    BundleService(session).freeze_revision(
        second_revision.source_bundle_revision_id,
        frozen_at=NOW + timedelta(minutes=1),
    )
    service = OpportunityUnitService(session)
    unit = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=first_revision.source_bundle_revision_id,
        seed=UnitSeed("A001", "POSITION", "Position A", "a" * 64),
        effective_from=NOW,
    )
    prior_pointer = unit.current_version_id
    current = service.append_version_cas(
        opportunity_unit_id=unit.opportunity_unit_id,
        expected_current_version_id=prior_pointer,
        opportunity_version=2,
        source_bundle_revision_id=second_revision.source_bundle_revision_id,
        effective_from=NOW + timedelta(minutes=1),
        canonical_label="Position A v2",
        identity_fingerprint="b" * 64,
    )

    assert unit.opportunity_version == 2
    assert unit.current_version_id == current.opportunity_unit_version_id
    with pytest.raises(DBAPIError, match="P9B_UNIT_CURRENT_VERSION_MISMATCH"):
        session.execute(
            text(
                "update opportunity_units set opportunity_version = 1 "
                "where opportunity_unit_id = :unit_id"
            ),
            {"unit_id": unit.opportunity_unit_id},
        )


def test_rekey_closes_current_alias_and_opens_new_current_window(session: Session) -> None:
    graph = seed_graph(session, suffix="rekey-window")
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    unit = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("A001", "POSITION", "Position A", "a" * 64),
        effective_from=NOW,
    )
    initial_alias = session.scalar(
        select(OpportunityUnitAlias).where(
            OpportunityUnitAlias.opportunity_unit_id == unit.opportunity_unit_id,
            OpportunityUnitAlias.alias_kind == "CURRENT",
        )
    )
    assert initial_alias is not None
    assert initial_alias.normalized_alias_key == "a001"
    assert initial_alias.valid_from == NOW
    assert initial_alias.valid_to is None

    effective_at = NOW + timedelta(hours=1)
    service.rekey_unit(
        opportunity_unit_id=unit.opportunity_unit_id,
        new_key="A002",
        source_bundle_revision_id=revision.source_bundle_revision_id,
        evidence_ref_ids=[graph.evidence_ref_id],
        confidence="DETERMINISTIC",
        effective_at=effective_at,
        reason_code="OFFICIAL_CODE_CORRECTION",
        actor_identity="human:reviewer-01",
    )
    aliases = tuple(
        session.scalars(
            select(OpportunityUnitAlias)
            .where(OpportunityUnitAlias.opportunity_unit_id == unit.opportunity_unit_id)
            .order_by(OpportunityUnitAlias.valid_from, OpportunityUnitAlias.alias_id)
        )
    )
    assert [(item.alias_kind, item.normalized_alias_key) for item in aliases] == [
        ("HISTORICAL", "a001"),
        ("CURRENT", "a002"),
    ]
    assert aliases[0].valid_from == NOW
    assert aliases[0].valid_to == effective_at
    assert aliases[1].valid_from == effective_at
    assert aliases[1].valid_to is None
    with pytest.raises(DBAPIError, match="alias history mutation rejected"):
        session.execute(
            text(
                "update opportunity_unit_aliases set display_alias_key = 'tampered' "
                "where alias_id = :alias_id"
            ),
            {"alias_id": aliases[0].alias_id},
        )


def test_rekey_requires_reason_and_accountable_actor(session: Session) -> None:
    graph = seed_graph(session, suffix="rekey-accountability")
    revision = frozen_bundle(session, graph)
    unit = OpportunityUnitService(session).create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("A001", "POSITION", "Position A", "a" * 64),
        effective_from=NOW,
    )

    with pytest.raises(UnitIdentityError, match="reason and accountable actor"):
        OpportunityUnitService(session).rekey_unit(
            opportunity_unit_id=unit.opportunity_unit_id,
            new_key="A002",
            source_bundle_revision_id=revision.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            confidence="DETERMINISTIC",
            effective_at=NOW + timedelta(hours=1),
            reason_code=" ",
            actor_identity=" ",
        )


def test_active_unit_cannot_commit_without_exact_current_alias(session: Session) -> None:
    graph = seed_graph(session, suffix="active-current-alias")
    revision = frozen_bundle(session, graph)
    unit = OpportunityUnitService(session).create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("A001", "POSITION", "Position A", "a" * 64),
        effective_from=NOW,
    )

    session.execute(
        text(
            "update opportunity_unit_aliases set alias_kind = 'HISTORICAL', valid_to = :now "
            "where opportunity_unit_id = :unit_id and alias_kind = 'CURRENT'"
        ),
        {"now": NOW + timedelta(hours=1), "unit_id": unit.opportunity_unit_id},
    )
    with pytest.raises(DBAPIError, match="P9B_ACTIVE_UNIT_CURRENT_ALIAS_MISMATCH"):
        session.execute(
            text("set constraints opportunity_unit_current_alias_exactly_one immediate")
        )


def test_singleton_split_preserves_identity_and_records_lineage(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    singleton = service.create_default_singleton(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW,
        canonical_label="Original singleton",
        identity_fingerprint="1" * 64,
    )

    event, children = service.split_singleton(
        opportunity_unit_id=singleton.opportunity_unit_id,
        expected_current_version_id=singleton.current_version_id,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        evidence_ref_ids=[graph.evidence_ref_id],
        units=[
            UnitSeed("A001", "POSITION", "Position A", "a" * 64),
            UnitSeed("B001", "POSITION", "Position B", "b" * 64),
        ],
        effective_at=NOW + timedelta(hours=1),
        reason_code="OFFICIAL_POSITION_TABLE",
        actor_identity="human-reviewer-01",
    )

    assert singleton.lifecycle_status == "RETIRED"
    assert singleton.opportunity_unit_id not in {item.opportunity_unit_id for item in children}
    assert len(children) == 2
    assert event.event_type == "SPLIT"
    singleton_aliases = tuple(
        session.scalars(
            select(OpportunityUnitAlias).where(
                OpportunityUnitAlias.opportunity_unit_id == singleton.opportunity_unit_id
            )
        )
    )
    assert len(singleton_aliases) == 1
    assert singleton_aliases[0].alias_kind == "HISTORICAL"
    assert singleton_aliases[0].valid_to == NOW + timedelta(hours=1)
    assert session.scalar(select(func.count()).select_from(OpportunityUnitLineageEvent)) == 1


def test_regular_merge_creates_new_unit_but_explicit_split_reversal_reuses_singleton(
    session: Session,
) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    singleton = service.create_default_singleton(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW,
        canonical_label="Original singleton",
        identity_fingerprint="1" * 64,
    )
    split_event, children = service.split_singleton(
        opportunity_unit_id=singleton.opportunity_unit_id,
        expected_current_version_id=singleton.current_version_id,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        evidence_ref_ids=[graph.evidence_ref_id],
        units=[
            UnitSeed("A001", "POSITION", "Position A", "a" * 64),
            UnitSeed("B001", "POSITION", "Position B", "b" * 64),
        ],
        effective_at=NOW + timedelta(hours=1),
        reason_code="OFFICIAL_POSITION_TABLE",
        actor_identity="human-reviewer-01",
    )

    reversal, reused = service.merge_units(
        opportunity_unit_ids=[item.opportunity_unit_id for item in children],
        source_bundle_revision_id=revision.source_bundle_revision_id,
        evidence_ref_ids=[graph.evidence_ref_id],
        target=UnitSeed("DEFAULT", "DEFAULT_SINGLETON", "Restored singleton", "c" * 64),
        effective_at=NOW + timedelta(hours=2),
        reason_code="OFFICIAL_SPLIT_REVERSAL",
        actor_identity="human-reviewer-02",
        reverses_split_event_id=split_event.lineage_event_id,
    )

    assert reversal.event_type == "REVERSAL"
    assert reused.opportunity_unit_id == singleton.opportunity_unit_id
    current_alias = session.scalar(
        select(OpportunityUnitAlias).where(
            OpportunityUnitAlias.opportunity_unit_id == reused.opportunity_unit_id,
            OpportunityUnitAlias.alias_kind == "CURRENT",
            OpportunityUnitAlias.valid_to.is_(None),
        )
    )
    assert current_alias is not None
    assert current_alias.normalized_alias_key == "default"

    second_graph = seed_graph(session, suffix="ordinary")
    second_revision = frozen_bundle(session, second_graph)
    second_service = OpportunityUnitService(session)
    first = second_service.create_unit(
        opportunity_id=second_graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=second_revision.source_bundle_revision_id,
        seed=UnitSeed("A", "POSITION", "A", "d" * 64),
        effective_from=NOW,
    )
    second = second_service.create_unit(
        opportunity_id=second_graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=second_revision.source_bundle_revision_id,
        seed=UnitSeed("B", "POSITION", "B", "e" * 64),
        effective_from=NOW,
    )
    _, merged = second_service.merge_units(
        opportunity_unit_ids=[first.opportunity_unit_id, second.opportunity_unit_id],
        source_bundle_revision_id=second_revision.source_bundle_revision_id,
        evidence_ref_ids=[second_graph.evidence_ref_id],
        target=UnitSeed("AB", "TRACK", "Merged AB", "f" * 64),
        effective_at=NOW + timedelta(hours=1),
        reason_code="OFFICIAL_MERGER",
        actor_identity="human-reviewer-03",
        reverses_split_event_id=None,
    )
    assert merged.opportunity_unit_id not in {
        first.opportunity_unit_id,
        second.opportunity_unit_id,
    }


def test_invalid_split_reversal_fails_before_retiring_any_source_unit(
    session: Session,
) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    singleton = service.create_default_singleton(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW,
        canonical_label="Original singleton",
        identity_fingerprint="1" * 64,
    )
    _, children = service.split_singleton(
        opportunity_unit_id=singleton.opportunity_unit_id,
        expected_current_version_id=singleton.current_version_id,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        evidence_ref_ids=[graph.evidence_ref_id],
        units=[
            UnitSeed("A001", "POSITION", "Position A", "a" * 64),
            UnitSeed("B001", "POSITION", "Position B", "b" * 64),
        ],
        effective_at=NOW + timedelta(hours=1),
        reason_code="OFFICIAL_POSITION_TABLE",
        actor_identity="human-reviewer-01",
    )
    pointers = {child.opportunity_unit_id: child.current_version_id for child in children}

    with pytest.raises(UnitIdentityError, match="existing SPLIT"):
        service.merge_units(
            opportunity_unit_ids=[child.opportunity_unit_id for child in children],
            source_bundle_revision_id=revision.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            target=UnitSeed(
                "DEFAULT",
                "DEFAULT_SINGLETON",
                "Invalid reversal",
                "c" * 64,
            ),
            effective_at=NOW + timedelta(hours=2),
            reason_code="UNSUPPORTED_REVERSAL",
            actor_identity="human-reviewer-02",
            reverses_split_event_id=uuid7(),
        )

    for child in children:
        session.refresh(child)
        assert child.lifecycle_status == "ACTIVE"
        assert child.current_version_id == pointers[child.opportunity_unit_id]


def test_split_child_collision_fails_before_retiring_singleton(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    singleton = service.create_default_singleton(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW,
        canonical_label="Original singleton",
        identity_fingerprint="1" * 64,
    )
    original_pointer = singleton.current_version_id

    with pytest.raises(UnitIdentityCollision, match="duplicate"):
        service.split_singleton(
            opportunity_unit_id=singleton.opportunity_unit_id,
            expected_current_version_id=original_pointer,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            units=[
                UnitSeed("A001", "POSITION", "Position A", "a" * 64),
                UnitSeed(" a001 ", "POSITION", "Position duplicate", "b" * 64),
            ],
            effective_at=NOW + timedelta(hours=1),
            reason_code="DUPLICATE_TEST",
            actor_identity="human-reviewer-01",
        )

    session.refresh(singleton)
    assert singleton.lifecycle_status == "ACTIVE"
    assert singleton.current_version_id == original_pointer


def test_collision_and_uncertain_rekey_fail_closed(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    unit = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed(" A001 ", "POSITION", "Position A", "a" * 64),
        effective_from=NOW,
    )

    with pytest.raises(UnitIdentityCollision):
        service.create_unit(
            opportunity_id=graph.opportunity_id,
            opportunity_version=1,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            seed=UnitSeed("a001", "POSITION", "Duplicate", "b" * 64),
            effective_from=NOW,
        )
    with pytest.raises(UnitIdentityCollision, match="UNCERTAIN"):
        service.rekey_unit(
            opportunity_unit_id=unit.opportunity_unit_id,
            new_key="A002",
            source_bundle_revision_id=revision.source_bundle_revision_id,
            evidence_ref_ids=[graph.evidence_ref_id],
            confidence="UNCERTAIN",
            effective_at=NOW + timedelta(hours=1),
            reason_code="SEMANTIC_GUESS",
            actor_identity="model-candidate",
        )


def test_unit_version_history_and_current_pointer_ownership_are_database_enforced(
    session: Session,
) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    first = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("A", "POSITION", "A", "a" * 64),
        effective_from=NOW,
    )
    second = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("B", "POSITION", "B", "b" * 64),
        effective_from=NOW,
    )
    assert first.current_version_id is not None
    assert second.current_version_id is not None
    first_pointer = first.current_version_id
    service.append_version_cas(
        opportunity_unit_id=first.opportunity_unit_id,
        expected_current_version_id=first_pointer,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        effective_from=NOW + timedelta(minutes=1),
        canonical_label="A v2",
        identity_fingerprint="c" * 64,
    )

    with pytest.raises(DBAPIError, match="P9B_UNIT_CURRENT_VERSION_MISMATCH"):
        session.execute(
            text(
                "update opportunity_units set current_version_id = :foreign_pointer "
                "where opportunity_unit_id = :unit_id"
            ),
            {
                "foreign_pointer": first_pointer,
                "unit_id": second.opportunity_unit_id,
            },
        )


def test_official_alias_reuse_overlapping_window_fails_closed(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    service = OpportunityUnitService(session)
    first = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("A", "POSITION", "A", "a" * 64),
        effective_from=NOW,
    )
    second = service.create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("B", "POSITION", "B", "b" * 64),
        effective_from=NOW,
    )
    session.add(
        OpportunityUnitAlias(
            alias_id=uuid7(),
            opportunity_id=graph.opportunity_id,
            opportunity_unit_id=first.opportunity_unit_id,
            normalized_alias_key="official-code-001",
            display_alias_key="OFFICIAL-CODE-001",
            alias_kind="OFFICIAL_CODE",
            valid_from=NOW,
            valid_to=None,
            evidence_ref_id=graph.evidence_ref_id,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            created_at=NOW,
        )
    )
    session.flush()
    session.add(
        OpportunityUnitAlias(
            alias_id=uuid7(),
            opportunity_id=graph.opportunity_id,
            opportunity_unit_id=second.opportunity_unit_id,
            normalized_alias_key="official-code-001",
            display_alias_key="OFFICIAL-CODE-001",
            alias_kind="OFFICIAL_CODE",
            valid_from=NOW + timedelta(minutes=1),
            valid_to=None,
            evidence_ref_id=graph.evidence_ref_id,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            created_at=NOW,
        )
    )

    with pytest.raises(DBAPIError, match="IDENTITY_COLLISION"):
        session.flush()


def test_unit_version_rows_are_insert_only(session: Session) -> None:
    graph = seed_graph(session)
    revision = frozen_bundle(session, graph)
    unit = OpportunityUnitService(session).create_unit(
        opportunity_id=graph.opportunity_id,
        opportunity_version=1,
        source_bundle_revision_id=revision.source_bundle_revision_id,
        seed=UnitSeed("A", "POSITION", "A", "a" * 64),
        effective_from=NOW,
    )
    assert unit.current_version_id is not None

    with pytest.raises(DBAPIError, match="immutable history"):
        session.execute(
            text(
                "update opportunity_unit_versions set canonical_label = 'mutated' "
                "where opportunity_unit_version_id = :version_id"
            ),
            {"version_id": unit.current_version_id},
        )
