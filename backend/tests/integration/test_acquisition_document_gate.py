from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.evaluations import EvaluationService
from deepaha.acquisition.pipeline import AcquisitionDocumentBlocked, advance_valid_artifact
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.documents.models import Document, ParseAttempt
from tests.integration.test_acquisition_evaluation_service import command, validation_result
from tests.integration.test_acquisition_fetchers import fetcher, request
from tests.integration.test_collection_service import ScriptedTransport, create_endpoint, response
from tests.integration.test_document_service import RAW_CONTENT, FakeParser, service_for

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    value = S3ObjectStore(Settings())
    value.ensure_bucket()
    return value


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def fetch_observation(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> tuple[UUID, UUID]:
    endpoint = create_endpoint(factory)
    fetched = fetcher(
        factory,
        object_store,
        ScriptedTransport([response(200, RAW_CONTENT, media_type="text/html; charset=utf-8")]),
    ).fetch(request(endpoint.endpoint_id, endpoint.source_id))
    assert fetched.observation_id is not None
    assert fetched.artifact_id is not None
    return fetched.observation_id, fetched.artifact_id


def test_valid_evaluation_advances_to_existing_document_service(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    observation_id, artifact_id = fetch_observation(factory, object_store)
    evaluation = EvaluationService(factory).record(command(observation_id))
    document_service = service_for(factory, object_store, FakeParser())

    result = advance_valid_artifact(
        session_factory=factory,
        document_service=document_service,
        acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
    )

    assert result.artifact_id == artifact_id
    assert result.outcome == "SUCCEEDED"
    assert result.document_id is not None


def test_invalid_evaluation_retains_raw_artifact_but_creates_no_document(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    observation_id, artifact_id = fetch_observation(factory, object_store)
    evaluation = EvaluationService(factory).record(
        command(observation_id, validation_result=validation_result(status="CAPTCHA_REQUIRED"))
    )
    document_service = service_for(factory, object_store, FakeParser())

    with pytest.raises(AcquisitionDocumentBlocked, match="ACQUISITION_DOCUMENT_BLOCKED"):
        advance_valid_artifact(
            session_factory=factory,
            document_service=document_service,
            acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
        )

    with factory() as session:
        artifact = session.get(RawArtifact, artifact_id)
        assert artifact is not None
        assert object_store.get_bytes(key=artifact.object_key) == RAW_CONTENT
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 0


def test_valid_document_transition_is_idempotent(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    observation_id, _ = fetch_observation(factory, object_store)
    evaluation = EvaluationService(factory).record(command(observation_id))
    parser = FakeParser()
    document_service = service_for(factory, object_store, parser)

    first = advance_valid_artifact(
        session_factory=factory,
        document_service=document_service,
        acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
    )
    second = advance_valid_artifact(
        session_factory=factory,
        document_service=document_service,
        acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
    )

    assert first.document_id == second.document_id
    assert second.created is False
    assert parser.calls == 1


def test_missing_evaluation_fails_without_parsing(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    parser = FakeParser()
    with pytest.raises(LookupError, match="AcquisitionEvaluation not found"):
        advance_valid_artifact(
            session_factory=factory,
            document_service=service_for(factory, object_store, parser),
            acquisition_evaluation_id=uuid7(),
        )
    assert parser.calls == 0
