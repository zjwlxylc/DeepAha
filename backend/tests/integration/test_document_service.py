from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid7

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.contracts.phase2 import (
    EvidenceLocatorV02,
    HtmlSelectorLocator,
    LegacyEvidenceLocator,
)
from deepaha.core.settings import Settings
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.documents.normalization import build_derived_text_key
from deepaha.documents.parser import ExpectedParseError, ParsedDocument
from deepaha.documents.service import (
    DerivedObjectConflict,
    DocumentService,
    ParseDocumentCommand,
    ParserSelectionError,
)
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
RAW_CONTENT = b"<html><main><p>Official notice</p></main></html>"
NORMALIZED_TEXT = "Official notice\n"


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeParser:
    name = "html_fake"

    def __init__(
        self,
        *,
        version: str = "0.2.0",
        parse_contract_version: str = "phase2-locator-contract-v0.2.0",
        parsed: ParsedDocument | None = None,
        error: ExpectedParseError | None = None,
    ) -> None:
        self.version = version
        self.parse_contract_version = parse_contract_version
        self.parsed = parsed or make_parsed_document()
        self.error = error
        self.calls = 0

    def supports(self, media_type: str) -> bool:
        return media_type.partition(";")[0].strip().lower() == "text/html"

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument:
        self.calls += 1
        assert content == RAW_CONTENT
        assert artifact_sha256 == sha256(RAW_CONTENT).hexdigest()
        if self.error is not None:
            raise self.error
        return self.parsed


def make_parsed_document(
    *,
    needs_review_reasons: tuple[str, ...] = (),
    locators: tuple[EvidenceLocatorV02, ...] | None = None,
) -> ParsedDocument:
    locator = HtmlSelectorLocator(
        schema_version="0.2.0",
        kind="html_selector",
        selector="main > p:nth-of-type(1)",
        text_sha256=sha256(b"Official notice").hexdigest(),
    )
    return ParsedDocument(
        title="Official notice",
        published_at=None,
        language="en",
        normalized_text=NORMALIZED_TEXT,
        locators=locators if locators is not None else (locator,),
        needs_review_reasons=needs_review_reasons,
    )


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


@pytest.fixture
def owned_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def create_artifact(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> tuple[UUID, str, str]:
    source_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://official.example/{source_id.hex}",
        authority_name="Synthetic official authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="Synthetic jurisdiction",
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(source)
        session.flush()
        result = import_raw_artifact(
            session=session,
            object_store=object_store,
            command=ImportRawArtifactCommand(
                source_id=source_id,
                requested_url="https://official.example/notice",
                resolved_url="https://official.example/notice",
                retrieved_at=NOW,
                http_status=200,
                media_type="text/html; charset=utf-8",
                content=RAW_CONTENT,
                collector_version="test/0.2.0",
                metadata_schema_version="0.2.0",
            ),
        )
        return (
            result.artifact.artifact_id,
            result.artifact.object_key,
            result.artifact.content_sha256,
        )


def service_for(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    *parsers: FakeParser,
) -> DocumentService:
    return DocumentService(
        session_factory=factory,
        object_store=object_store,
        parsers=parsers,
        clock=FixedClock(),
    )


def test_success_persists_derived_text_document_evidence_and_attempt(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, raw_key, raw_sha = create_artifact(owned_session_factory, object_store)
    parser = FakeParser()
    service = service_for(owned_session_factory, object_store, parser)

    result = service.parse(ParseDocumentCommand(artifact_id=artifact_id))

    assert result.created is True
    assert result.outcome == "SUCCEEDED"
    assert result.document_id is not None
    assert result.error_code is None
    derived_key = build_derived_text_key(
        raw_sha,
        parser.name,
        parser.version,
        parser.parse_contract_version,
    )
    assert result.extracted_text_uri == f"s3://deepaha-raw/{derived_key}"
    assert object_store.get_bytes(key=derived_key) == NORMALIZED_TEXT.encode()
    assert object_store.get_bytes(key=raw_key) == RAW_CONTENT
    with owned_session_factory() as session:
        artifact = session.get(RawArtifact, artifact_id)
        assert artifact is not None
        assert (artifact.object_key, artifact.content_sha256) == (raw_key, raw_sha)
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(EvidenceRef)) == 1
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 1
        document = session.get(Document, result.document_id)
        assert document is not None
        assert document.parse_contract_version == parser.parse_contract_version
        assert document.document_parse_key is not None
        evidence = session.scalar(select(EvidenceRef))
        assert evidence is not None
        assert evidence.locator_schema_version == "0.2.0"
        assert evidence.locator_kind == "html_selector"
        assert evidence.locator_value is None
        assert evidence.locator_payload is not None
        assert evidence.locator_payload["selector"] == "main > p:nth-of-type(1)"


def test_replay_returns_same_document_without_parsing_again(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)
    parser = FakeParser()
    service = service_for(owned_session_factory, object_store, parser)

    first = service.parse(ParseDocumentCommand(artifact_id=artifact_id))
    second = service.parse(ParseDocumentCommand(artifact_id=artifact_id))

    assert first.document_id == second.document_id
    assert first.parse_attempt_id == second.parse_attempt_id
    assert first.created is True
    assert second.created is False
    assert parser.calls == 1
    with owned_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 1


def test_new_parser_version_creates_new_document(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)

    first = service_for(owned_session_factory, object_store, FakeParser(version="0.2.0")).parse(
        ParseDocumentCommand(artifact_id=artifact_id)
    )
    second = service_for(owned_session_factory, object_store, FakeParser(version="0.2.1")).parse(
        ParseDocumentCommand(artifact_id=artifact_id)
    )

    assert first.document_id != second.document_id
    with owned_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 2
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 2


def test_new_parse_contract_version_creates_new_immutable_document(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)

    first = service_for(
        owned_session_factory,
        object_store,
        FakeParser(parse_contract_version="phase2-locator-contract-v0.2.0"),
    ).parse(ParseDocumentCommand(artifact_id=artifact_id))
    second = service_for(
        owned_session_factory,
        object_store,
        FakeParser(parse_contract_version="p9b-document-block-contract-v0.8.0"),
    ).parse(ParseDocumentCommand(artifact_id=artifact_id))

    assert first.document_id != second.document_id
    with owned_session_factory() as session:
        documents = tuple(session.scalars(select(Document).order_by(Document.document_id)))
        attempts = tuple(
            session.scalars(select(ParseAttempt).order_by(ParseAttempt.parse_attempt_id))
        )
        assert len(documents) == len(attempts) == 2
        assert {item.parse_contract_version for item in documents} == {
            "phase2-locator-contract-v0.2.0",
            "p9b-document-block-contract-v0.8.0",
        }
        assert len({item.document_parse_key for item in documents}) == 2


def test_expected_failure_persists_failed_attempt_without_document(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)
    parser = FakeParser(error=ExpectedParseError("HTML_TEXT_EMPTY"))

    result = service_for(owned_session_factory, object_store, parser).parse(
        ParseDocumentCommand(artifact_id=artifact_id)
    )

    assert result.outcome == "FAILED"
    assert result.document_id is None
    assert result.error_code == "HTML_TEXT_EMPTY"
    with owned_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 1


def test_review_reason_persists_needs_review_with_document(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)
    parser = FakeParser(
        parsed=make_parsed_document(needs_review_reasons=("PDF_PAGE_TEXT_MISSING",))
    )

    result = service_for(owned_session_factory, object_store, parser).parse(
        ParseDocumentCommand(artifact_id=artifact_id)
    )

    assert result.outcome == "NEEDS_REVIEW"
    assert result.document_id is not None
    assert result.error_code == "PDF_PAGE_TEXT_MISSING"


def test_conflicting_derived_bytes_never_overwrite(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, raw_sha = create_artifact(owned_session_factory, object_store)
    parser = FakeParser(version="0.2.conflict")
    derived_key = build_derived_text_key(
        raw_sha,
        parser.name,
        parser.version,
        parser.parse_contract_version,
    )
    conflicting = b"different derived bytes"
    object_store.put_bytes_if_absent(
        key=derived_key,
        content=conflicting,
        media_type="text/plain; charset=utf-8",
        sha256=sha256(conflicting).hexdigest(),
    )

    with pytest.raises(DerivedObjectConflict) as captured:
        service_for(owned_session_factory, object_store, parser).parse(
            ParseDocumentCommand(artifact_id=artifact_id)
        )

    assert captured.value.code == "DERIVED_OBJECT_CONFLICT"
    assert object_store.get_bytes(key=derived_key) == conflicting
    with owned_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 0


def test_parser_selection_requires_exactly_one_supporting_parser(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)

    with pytest.raises(ParserSelectionError, match="exactly one parser"):
        service_for(owned_session_factory, object_store).parse(
            ParseDocumentCommand(artifact_id=artifact_id)
        )
    with pytest.raises(ParserSelectionError, match="exactly one parser"):
        service_for(
            owned_session_factory,
            object_store,
            FakeParser(),
            FakeParser(version="0.2.1"),
        ).parse(ParseDocumentCommand(artifact_id=artifact_id))


@pytest.mark.parametrize(
    "parsed",
    [
        replace(make_parsed_document(), normalized_text="not normalized  \r\n"),
        make_parsed_document(locators=()),
        make_parsed_document(
            locators=(
                cast(
                    EvidenceLocatorV02,
                    {"schema_version": "0.2.0", "kind": "html_selector"},
                ),
            )
        ),
        make_parsed_document(locators=(LegacyEvidenceLocator(kind="full_document", value="*"),)),
    ],
)
def test_programmer_contract_errors_raise_without_stable_attempt(
    parsed: ParsedDocument,
    owned_session_factory: sessionmaker[Session],
    object_store: S3ObjectStore,
) -> None:
    artifact_id, _, _ = create_artifact(owned_session_factory, object_store)

    with pytest.raises((ValueError, ValidationError), match="normalized|locator|Field required"):
        service_for(owned_session_factory, object_store, FakeParser(parsed=parsed)).parse(
            ParseDocumentCommand(artifact_id=artifact_id)
        )

    with owned_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 0
