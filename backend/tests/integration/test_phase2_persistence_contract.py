from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.opportunities.models import Opportunity
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
SHA_ONE = "1" * 64
SHA_TWO = "2" * 64
OPPORTUNITY_TYPES = {
    "PUBLIC_INSTITUTION_JOB",
    "STATE_OWNED_ENTERPRISE_JOB",
    "CIVIL_SERVICE",
    "GRASSROOTS_PROGRAM",
    "YOUTH_POLICY_BENEFIT",
    "POSTGRAD_RECOMMENDATION",
    "ADMISSION_CHANGE",
    "COMPETITION",
    "RESEARCH_PROGRAM",
    "SCHOLARSHIP",
    "YOUTH_DEVELOPMENT_PROGRAM",
}


def make_source(*, suffix: str) -> Source:
    return Source(
        source_id=uuid7(),
        public_id=f"src_{suffix.zfill(32)}",
        canonical_url=f"https://{suffix}.example.gov/",
        authority_name=f"Synthetic authority {suffix}",
        tier="OFFICIAL_PRIMARY",
        jurisdiction=None,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def make_endpoint(owner: Source) -> SourceEndpoint:
    return SourceEndpoint(
        endpoint_id=uuid7(),
        source_id=owner.source_id,
        url=f"{owner.canonical_url}notices",
        allowed_hosts=[f"{owner.public_id[-1]}.example.gov"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=21600,
        timeout_seconds=30,
        max_attempts=3,
        robots_url=f"{owner.canonical_url}robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=NOW,
        content_use_basis="OFFICIAL_PUBLIC_ACCESS",
        license_name=None,
        license_url=None,
        attribution=None,
        fixture_storage_allowed=False,
        usage_note="Synthetic persistence fixture.",
        policy_version="2026-08-21.1",
        active=True,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_artifact(owner: Source, *, sha256: str = SHA_ONE) -> RawArtifact:
    return RawArtifact(
        artifact_id=uuid7(),
        source_id=owner.source_id,
        requested_url=f"{owner.canonical_url}notices",
        resolved_url=f"{owner.canonical_url}notices",
        retrieved_at=NOW,
        http_status=200,
        media_type="text/html",
        content_sha256=sha256,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{sha256[:2]}/{sha256}",
        byte_size=128,
        collector_version="test/0.2.0",
        metadata_schema_version="0.2.0",
    )


def make_observation(
    endpoint: SourceEndpoint,
    artifact: RawArtifact | None,
    *,
    source_id: UUID | None = None,
    collection_run_id: UUID | None = None,
    outcome: str = "SUCCEEDED",
    http_status: int | None = 200,
    error_code: str | None = None,
) -> CaptureObservation:
    return CaptureObservation(
        observation_id=uuid7(),
        collection_run_id=collection_run_id or uuid7(),
        attempt_number=1,
        endpoint_id=endpoint.endpoint_id,
        source_id=source_id or endpoint.source_id,
        requested_url=endpoint.url,
        resolved_url=endpoint.url,
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        outcome=outcome,
        http_status=http_status,
        response_etag=None,
        response_last_modified=None,
        artifact_id=artifact.artifact_id if artifact is not None else None,
        error_code=error_code,
        collector_name="test_collector",
        collector_version="0.2.0",
        policy_version=endpoint.policy_version,
    )


def make_document(artifact: RawArtifact, *, version: str = "0.2.0") -> Document:
    return Document(
        document_id=uuid7(),
        artifact_id=artifact.artifact_id,
        title="Synthetic document",
        published_at=None,
        language="und",
        extracted_text_uri=None,
        parser_name="html_lxml",
        parser_version=version,
        parse_confidence=None,
        created_at=NOW,
    )


def persist_capture_graph(session: Session) -> tuple[SourceEndpoint, RawArtifact]:
    owner = make_source(suffix="1")
    endpoint = make_endpoint(owner)
    artifact = make_artifact(owner)
    session.add(owner)
    session.flush()
    session.add_all([endpoint, artifact])
    session.flush()
    return endpoint, artifact


def test_phase2_tables_and_locator_columns_exist(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    assert {"source_endpoints", "capture_observations", "parse_attempts"} <= set(
        inspector.get_table_names()
    )
    assert {column["name"] for column in inspector.get_columns("evidence_refs")} >= {
        "locator_schema_version",
        "locator_payload",
    }


def test_two_observations_can_reference_one_artifact(session: Session) -> None:
    endpoint, artifact = persist_capture_graph(session)
    session.add_all(
        [
            make_observation(endpoint, artifact),
            make_observation(endpoint, artifact),
        ]
    )
    session.flush()

    assert session.scalar(select(func.count()).select_from(CaptureObservation)) == 2
    artifact_ids = session.scalars(
        select(CaptureObservation.artifact_id).order_by(CaptureObservation.started_at)
    ).all()
    assert artifact_ids == [artifact.artifact_id, artifact.artifact_id]
    assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1


def test_failed_observation_rejects_artifact(session: Session) -> None:
    endpoint, artifact = persist_capture_graph(session)
    session.add(
        make_observation(
            endpoint,
            artifact,
            outcome="FAILED",
            http_status=None,
            error_code="NETWORK_TIMEOUT",
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_not_modified_requires_artifact(session: Session) -> None:
    endpoint, _ = persist_capture_graph(session)
    session.add(make_observation(endpoint, None, outcome="NOT_MODIFIED", http_status=304))

    with pytest.raises(IntegrityError):
        session.flush()


def test_capture_endpoint_source_mismatch_is_rejected(session: Session) -> None:
    owner = make_source(suffix="1")
    other = make_source(suffix="2")
    endpoint = make_endpoint(owner)
    artifact = make_artifact(other)
    session.add_all([owner, other])
    session.flush()
    session.add_all([endpoint, artifact])
    session.flush()
    session.add(make_observation(endpoint, artifact, source_id=other.source_id))

    with pytest.raises(IntegrityError):
        session.flush()


def test_capture_artifact_source_mismatch_is_rejected(session: Session) -> None:
    owner = make_source(suffix="1")
    other = make_source(suffix="2")
    endpoint = make_endpoint(owner)
    artifact = make_artifact(other)
    session.add_all([owner, other])
    session.flush()
    session.add_all([endpoint, artifact])
    session.flush()
    session.add(make_observation(endpoint, artifact))

    with pytest.raises(IntegrityError):
        session.flush()


def test_parse_attempt_document_artifact_mismatch_is_rejected(session: Session) -> None:
    owner = make_source(suffix="1")
    first_artifact = make_artifact(owner)
    second_artifact = make_artifact(owner, sha256=SHA_TWO)
    document = make_document(first_artifact)
    session.add(owner)
    session.flush()
    session.add_all([first_artifact, second_artifact])
    session.flush()
    session.add(document)
    session.flush()
    session.add(
        ParseAttempt(
            parse_attempt_id=uuid7(),
            artifact_id=second_artifact.artifact_id,
            parser_name="html_lxml",
            parser_version="0.2.0",
            started_at=NOW,
            completed_at=NOW,
            outcome="SUCCEEDED",
            document_id=document.document_id,
            error_code=None,
            input_media_type="text/html",
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_failed_parse_attempt_rejects_document(session: Session) -> None:
    owner = make_source(suffix="1")
    artifact = make_artifact(owner)
    document = make_document(artifact)
    session.add(owner)
    session.flush()
    session.add(artifact)
    session.flush()
    session.add(document)
    session.flush()
    session.add(
        ParseAttempt(
            parse_attempt_id=uuid7(),
            artifact_id=artifact.artifact_id,
            parser_name="html_lxml",
            parser_version="0.2.0",
            started_at=NOW,
            completed_at=NOW,
            outcome="FAILED",
            document_id=document.document_id,
            error_code="HTML_TEXT_EMPTY",
            input_media_type="text/html",
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_legacy_and_structured_locators_are_persisted(session: Session) -> None:
    owner = make_source(suffix="1")
    artifact = make_artifact(owner)
    document = make_document(artifact)
    session.add(owner)
    session.flush()
    session.add(artifact)
    session.flush()
    session.add(document)
    session.flush()
    session.add_all(
        [
            EvidenceRef(
                evidence_ref_id=uuid7(),
                document_id=document.document_id,
                artifact_id=artifact.artifact_id,
                locator_kind="full_document",
                locator_value="*",
                locator_schema_version="0.1.0",
                locator_payload=None,
                quote_sha256=SHA_ONE,
            ),
            EvidenceRef(
                evidence_ref_id=uuid7(),
                document_id=document.document_id,
                artifact_id=artifact.artifact_id,
                locator_kind="html_selector",
                locator_value=None,
                locator_schema_version="0.2.0",
                locator_payload={
                    "schema_version": "0.2.0",
                    "kind": "html_selector",
                    "selector": "main > p:nth-of-type(1)",
                    "text_sha256": SHA_ONE,
                },
                quote_sha256=SHA_ONE,
            ),
        ]
    )
    session.flush()

    assert session.scalar(select(func.count()).select_from(EvidenceRef)) == 2


def test_malformed_structured_locator_is_rejected(session: Session) -> None:
    owner = make_source(suffix="1")
    artifact = make_artifact(owner)
    document = make_document(artifact)
    session.add(owner)
    session.flush()
    session.add(artifact)
    session.flush()
    session.add(document)
    session.flush()
    session.add(
        EvidenceRef(
            evidence_ref_id=uuid7(),
            document_id=document.document_id,
            artifact_id=artifact.artifact_id,
            locator_kind="pdf_page_text",
            locator_value=None,
            locator_schema_version="0.2.0",
            locator_payload={
                "schema_version": "0.2.0",
                "kind": "pdf_page_text",
                "page_number": 0,
                "text_start": 10,
                "text_end": 10,
                "text_sha256": SHA_ONE,
            },
            quote_sha256=SHA_ONE,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def make_opportunity(value: str) -> Opportunity:
    entity_id = uuid7()
    return Opportunity(
        opportunity_id=entity_id,
        public_id=f"opp_{entity_id.hex}",
        type=value,
        canonical_title=f"Synthetic {value}",
        issuer_name="Synthetic authority",
        jurisdiction=None,
        current_version=None,
        status="UNKNOWN",
        publication_status="INTERNAL",
        created_at=NOW,
        updated_at=NOW,
    )


def test_all_v02_opportunity_types_are_accepted(session: Session) -> None:
    session.add_all([make_opportunity(value) for value in OPPORTUNITY_TYPES])
    session.flush()

    assert session.scalar(select(func.count()).select_from(Opportunity)) == 11


def test_unknown_opportunity_type_is_rejected(session: Session) -> None:
    session.add(make_opportunity("GENERIC_JOB"))

    with pytest.raises(IntegrityError):
        session.flush()
