"""Generic persistence checks against real PostgreSQL and owned local raw objects."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from uuid import uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.documents.blocks import block_hash, evidence_binding_hash
from deepaha.documents.html import P9BHtmlDocumentParser
from deepaha.documents.models import DocumentBlock, EvidenceRef
from deepaha.documents.reader import ReaderDocumentParser, replay_reader_anchor
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.evidence_verification.adapters.html import HtmlAdapter
from deepaha.evidence_verification.binding import PreparedDocumentEvidence
from deepaha.evidence_verification.contracts import ArtifactInput
from deepaha.evidence_verification.registry import AdapterRegistry
from tests.evidence_verification.test_verifier import SyntheticAdapter
from tests.integration.test_investigation_store import StoreHarness, _pending, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


@pytest.mark.parametrize("overlong", [False, True])
def test_new_registered_format_persists_without_schema_edits_and_expected_failures_are_recorded(
    harness: StoreHarness, overlong: bool
) -> None:
    h = harness
    adapter = SyntheticAdapter()
    content = b"Exact new format content"
    media = adapter.media_types[0]
    if overlong:
        content = (
            ("<" + "x" * 100 + ">") * 190 + "value" + ("</" + "x" * 100 + ">") * 190
        ).encode()
        media = "text/html"
    with h.factory.begin() as session:
        raw = import_raw_artifact(
            session=session,
            object_store=h.objects,
            command=ImportRawArtifactCommand(
                source_id=h.command.source_id,
                requested_url="https://example.gov/test",
                resolved_url="https://example.gov/test",
                retrieved_at=h.clock(),
                http_status=200,
                media_type=media,
                content=content,
                collector_version="synthetic-test/1",
                metadata_schema_version="0.2.0",
            ),
        ).artifact
    parser = ReaderDocumentParser(HtmlAdapter() if overlong else adapter)
    result = DocumentService(
        session_factory=h.factory, object_store=h.objects, parsers=[parser]
    ).parse(ParseDocumentCommand(raw.artifact_id))
    if overlong:
        assert result.outcome == "FAILED" and result.error_code == "READER_ANCHOR_INVALID"
        assert result.document_id is None
    else:
        assert result.document_id is not None
        with h.factory() as session:
            prepared = PreparedDocumentEvidence(
                session,
                h.objects,
                AdapterRegistry((adapter,)),
                document_id=result.document_id,
                source_url="https://example.gov/test",
            )
            reads = adapter.reads
            for _ in range(3):
                bound = prepared.verify("Exact new format content", {"line": 1})
                assert bound.verification.verdict == "PASS" and bound.evidence_ref_id is not None
            assert adapter.reads == reads  # The same replay cache serves each quote.


def test_generic_parse_coexists_with_legacy_and_replays_the_immutable_evidence(
    harness: StoreHarness,
) -> None:
    h = harness
    _pending(h)
    with h.factory() as session:
        raw = session.scalar(select(RawArtifact))
        assert raw is not None
    old = DocumentService(
        session_factory=h.factory, object_store=h.objects, parsers=[P9BHtmlDocumentParser()]
    ).parse(ParseDocumentCommand(raw.artifact_id))
    service = DocumentService(
        session_factory=h.factory,
        object_store=h.objects,
        parsers=[ReaderDocumentParser(HtmlAdapter())],
    )
    result = service.parse(ParseDocumentCommand(raw.artifact_id))
    assert result.outcome == "SUCCEEDED" and result.document_id != old.document_id
    assert result.document_parse_key != old.document_parse_key
    assert not service.parse(ParseDocumentCommand(raw.artifact_id)).created
    assert result.document_id is not None
    with h.factory() as session:
        prepared = PreparedDocumentEvidence(
            session,
            h.objects,
            default_registry(),
            document_id=result.document_id,
            source_url="https://example.gov/notice",
        )
        parser_projection = (
            ReaderDocumentParser(HtmlAdapter())
            .parse(
                artifact_sha256=raw.content_sha256, content=h.objects.get_bytes(key=raw.object_key)
            )
            .blocks[0]
        )
        bound = prepared.verify(parser_projection.canonical_text_or_value, {"selector": "body"})
        assert (
            bound.verification.verdict == "PASS"
            and bound.block_id is not None
            and bound.evidence_ref_id is not None
        )
        uncertain = prepared.verify(
            parser_projection.canonical_text_or_value, {"selector": "body", "human_verify": True}
        )
        assert uncertain.verification.verdict == "UNVERIFIED" and uncertain.evidence_ref_id is None
    artifact = ArtifactInput(
        str(raw.artifact_id),
        "text/html",
        "https://example.gov/notice",
        raw.content_sha256,
        h.objects.get_bytes(key=raw.object_key),
    )
    with h.factory() as session:
        blocks = list(
            session.scalars(
                select(DocumentBlock).where(DocumentBlock.document_id == result.document_id)
            )
        )
        assert blocks
        for block in blocks:
            ref = session.get(EvidenceRef, block.evidence_ref_id)
            assert ref is not None and ref.locator_schema_version == "0.9.0"
            assert ref.quote_sha256 == sha256(block.canonical_text_or_value.encode()).hexdigest()
            projection = replay_reader_anchor(
                default_registry(), artifact, block.structural_locator
            )
            assert projection.text == block.canonical_text_or_value
        old_ref = session.get(EvidenceRef, old.evidence_ref_ids[0])
        assert old_ref is not None and old_ref.locator_schema_version == "0.8.0"
    with pytest.raises(RuntimeError, match="Reader anchors with evidence history"):
        command.downgrade(Config("alembic.ini"), "20260907_0037")
    with pytest.raises(DBAPIError, match="immutable"), h.factory.begin() as session:
        session.execute(
            text(
                "update document_blocks set canonical_text_or_value = 'changed' "
                "where block_id = :id"
            ),
            {"id": result.document_block_ids[0]},
        )
    with pytest.raises(DBAPIError, match="immutable"), h.factory.begin() as session:
        session.execute(
            text(
                "update evidence_refs set locator_payload = jsonb_set(locator_payload, "
                "'{structural_locator,representation_sha256}', to_jsonb(repeat('0',64))) "
                "where evidence_ref_id = :id"
            ),
            {"id": result.evidence_ref_ids[0]},
        )


@pytest.mark.parametrize(
    "forgery", ["extra", "type", "reader", "value", "raw", "block_hash", "binding_hash"]
)
def test_database_rejects_forged_generic_envelopes_and_provenance(
    harness: StoreHarness, forgery: str
) -> None:
    h = harness
    _pending(h)
    with h.factory() as session:
        raw = session.scalar(select(RawArtifact))
        assert raw is not None
    parser = ReaderDocumentParser(HtmlAdapter())
    parsed = parser.parse(
        h.objects.get_bytes(key=raw.object_key), artifact_sha256=raw.content_sha256
    )
    result = DocumentService(
        session_factory=h.factory, object_store=h.objects, parsers=[parser]
    ).parse(ParseDocumentCommand(raw.artifact_id))
    with h.factory() as session:
        original = session.get(DocumentBlock, result.document_block_ids[0])
        assert original is not None
        block_values = {c.name: getattr(original, c.name) for c in original.__table__.columns}
        reference = session.get(EvidenceRef, original.evidence_ref_id)
        assert reference is not None
        ref_values = {c.name: getattr(reference, c.name) for c in reference.__table__.columns}
    anchor = deepcopy(parsed.blocks[0].structural_locator)
    if forgery == "extra":
        anchor["unregistered_extension"] = "forged"
    if forgery == "type":
        anchor["text_end"] = "12"
    if forgery == "reader":
        reader = anchor["reader"]
        assert isinstance(reader, dict)
        reader["version"] = "forged"
    if forgery == "value":
        anchor["projection_sha256"] = "0" * 64
    if forgery == "raw":
        anchor["artifact_sha256"] = "0" * 64
    block_id, ref_id = uuid7(), uuid7()
    ordinal = len(parsed.blocks) + 1
    updated = replace(parsed.blocks[0], structural_locator=anchor)
    digest = block_hash(
        document_parse_key=result.document_parse_key, ordinal=ordinal, block=updated
    )
    binding_digest = evidence_binding_hash(
        block_id=str(block_id),
        document_parse_key=result.document_parse_key,
        structural_locator=anchor,
        block_hash_value=digest,
    )
    payload = deepcopy(reference.locator_payload)
    assert isinstance(payload, dict)
    payload.update(block_id=str(block_id), structural_locator=anchor)
    ref_values.update(evidence_ref_id=ref_id, locator_payload=payload)
    block_values.update(
        block_id=block_id,
        evidence_ref_id=ref_id,
        ordinal=ordinal,
        structural_locator=anchor,
        block_hash="0" * 64 if forgery == "block_hash" else digest,
        evidence_binding_hash="0" * 64 if forgery == "binding_hash" else binding_digest,
    )
    with pytest.raises(DBAPIError), h.factory.begin() as session:
        session.add(EvidenceRef(**ref_values))
        session.flush()
        session.add(DocumentBlock(**block_values))
        session.flush()


def test_migration_roundtrip_restores_constraints_and_unique_head(harness: StoreHarness) -> None:
    # No rows seeded: tests own the database, never a user database.
    config = Config("alembic.ini")
    command.downgrade(config, "20260907_0037")
    with harness.factory() as session:
        before = session.scalar(
            text(
                "select pg_get_expr(conbin, conrelid) from pg_constraint "
                "where conname = 'ck_evidence_refs_locator_schema_form'"
            )
        )
    command.upgrade(config, "head")

    command.downgrade(config, "20260907_0037")
    with harness.factory() as session:
        after = session.scalar(
            text(
                "select pg_get_expr(conbin, conrelid) from pg_constraint "
                "where conname = 'ck_evidence_refs_locator_schema_form'"
            )
        )
    assert before == after
    command.upgrade(config, "head")


def test_replay_rejects_replaced_derived_bytes_even_with_matching_storage_metadata(
    harness: StoreHarness,
) -> None:
    h = harness
    _pending(h)
    with h.factory() as session:
        raw = session.scalar(select(RawArtifact))
        assert raw is not None
    result = DocumentService(
        session_factory=h.factory,
        object_store=h.objects,
        parsers=[ReaderDocumentParser(HtmlAdapter())],
    ).parse(ParseDocumentCommand(raw.artifact_id))
    assert result.document_id is not None and result.extracted_text_uri is not None
    from urllib.parse import urlsplit

    key = urlsplit(result.extracted_text_uri).path.lstrip("/")
    old = h.objects.stat(key=key)
    h.objects.delete_if_matches(key=key, sha256=old.sha256)
    changed = b"Forged derived text; all object metadata matches these forged bytes."
    h.objects.put_bytes_if_absent(
        key=key, content=changed, sha256=sha256(changed).hexdigest(), media_type="text/plain"
    )
    with (
        pytest.raises(LookupError, match="DERIVED_DOCUMENT_INTEGRITY_FAILED"),
        h.factory() as session,
    ):
        PreparedDocumentEvidence(
            session,
            h.objects,
            default_registry(),
            document_id=result.document_id,
            source_url="https://example.gov/notice",
        )
