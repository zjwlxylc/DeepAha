import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.contracts.phase2 import HtmlSelectorLocator
from deepaha.core.settings import Settings
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.locator import replay_html_locator
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.opportunities.models import Opportunity
from deepaha.sources.collector import CollectionRunner
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint
from deepaha.sources.transport import HttpRequest, HttpResponse

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parents[1] / "fixtures" / "official"
HTML = FIXTURES / "civil-service-fast-stream-news-2025.html"
MANIFEST = FIXTURES / "civil-service-fast-stream-news-2025-html.manifest.json"
FIXED_SHA256 = "b7b92f5e24f496bf462aeb6669cd117fbc83d2f691d6bf2a42024085a58d3468"


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FixtureTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[HttpRequest] = []

    def get_once(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.response


class PublicResolver:
    def resolve(self, host: str) -> tuple[str, ...]:
        assert host == "www.gov.uk"
        return ("151.101.76.144",)


class NoSleep:
    def sleep(self, seconds: int) -> None:
        raise AssertionError(f"successful fixture capture must not sleep: {seconds}")


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


@pytest.fixture
def owned_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def test_official_html_flows_through_raw_observation_and_parse_evidence(
    owned_session_factory: sessionmaker[Session],
    object_store: S3ObjectStore,
) -> None:
    content = HTML.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    captured_at = datetime.fromisoformat(
        manifest["retrieved_at"].replace("Z", "+00:00")
    ).astimezone(UTC)
    source_id = uuid7()
    endpoint_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=manifest["requested_url"],
        authority_name="Government Skills and Civil Service Fast Stream",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="United Kingdom",
        active=True,
        created_at=captured_at,
        updated_at=captured_at,
    )
    endpoint = SourceEndpoint(
        endpoint_id=endpoint_id,
        source_id=source_id,
        url=manifest["requested_url"],
        allowed_hosts=["www.gov.uk"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=21600,
        timeout_seconds=30,
        max_attempts=3,
        robots_url="https://www.gov.uk/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=captured_at,
        content_use_basis="OPEN_LICENSE",
        license_name=manifest["license"]["name"],
        license_url=manifest["license"]["url"],
        attribution=manifest["license"]["attribution"],
        fixture_storage_allowed=True,
        usage_note="Licensed fixed HTML fixture only; linked assets are excluded.",
        policy_version="2026-08-21.1",
        active=True,
        verified_at=captured_at,
        created_at=captured_at,
        updated_at=captured_at,
    )
    with owned_session_factory.begin() as session:
        session.add_all([source, endpoint])

    transport = FixtureTransport(
        HttpResponse(
            status_code=200,
            url=manifest["resolved_url"],
            media_type=manifest["media_type"],
            etag='"fixed-html"',
            last_modified=None,
            location=None,
            body=content,
        )
    )
    runner = CollectionRunner(
        session_factory=owned_session_factory,
        object_store=object_store,
        transport=transport,
        resolver=PublicResolver(),
        clock=FixedClock(captured_at),
        sleeper=NoSleep(),
        collector_name="phase2_fixture",
        collector_version="0.2.0",
    )

    collected = runner.collect(endpoint_id)
    artifact_id = collected.attempts[0].artifact_id
    assert artifact_id is not None
    with owned_session_factory() as session:
        artifact_before = session.get(RawArtifact, artifact_id)
        assert artifact_before is not None
        raw_identity = (
            artifact_before.object_key,
            artifact_before.content_sha256,
            artifact_before.byte_size,
        )
    raw_before = object_store.get_bytes(key=raw_identity[0])

    parsed = DocumentService(
        session_factory=owned_session_factory,
        object_store=object_store,
        parsers=(LxmlHtmlParser(),),
        clock=FixedClock(captured_at),
    ).parse(ParseDocumentCommand(artifact_id=artifact_id))

    assert parsed.outcome == "SUCCEEDED"
    assert parsed.document_id is not None
    assert parsed.extracted_text_uri is not None
    assert not parsed.extracted_text_uri.endswith(raw_identity[0])
    with owned_session_factory() as session:
        artifact_after = session.get(RawArtifact, artifact_id)
        document = session.get(Document, parsed.document_id)
        observation = session.scalar(select(CaptureObservation))
        attempt = session.scalar(select(ParseAttempt))
        evidence_refs = list(
            session.scalars(
                select(EvidenceRef)
                .where(EvidenceRef.document_id == parsed.document_id)
                .order_by(EvidenceRef.evidence_ref_id)
            )
        )
        assert artifact_after is not None
        assert document is not None
        assert observation is not None
        assert attempt is not None
        assert (
            artifact_after.object_key,
            artifact_after.content_sha256,
            artifact_after.byte_size,
        ) == raw_identity
        assert document.artifact_id == artifact_id
        assert (
            document.title == "Civil Service Fast Stream named UK's top graduate employer - GOV.UK"
        )
        assert document.published_at is None
        assert document.language == "en"
        assert attempt.outcome == "SUCCEEDED"
        assert observation.outcome == "SUCCEEDED"
        assert len(evidence_refs) == 28
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourceEndpoint)) == 1
        assert session.scalar(select(func.count()).select_from(CaptureObservation)) == 1
        assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 1
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 0
        for evidence_ref in evidence_refs:
            locator = HtmlSelectorLocator.model_validate(evidence_ref.locator_payload)
            assert replay_html_locator(content, locator)

    assert transport.requests[0].url == manifest["requested_url"]
    assert raw_before == content == object_store.get_bytes(key=raw_identity[0])
    assert sha256(content).hexdigest() == FIXED_SHA256 == raw_identity[1]
