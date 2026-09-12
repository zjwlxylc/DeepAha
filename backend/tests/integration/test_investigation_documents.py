"""Synthetic document preparation uses real persistence without promoting facts."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import func, select

from deepaha.documents.docx import DOCX_MEDIA_TYPE
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef, ParseAttempt
from deepaha.documents.service import DocumentService, ParseDocumentCommand, ParseDocumentResult
from deepaha.documents.spreadsheet import XLSX_MEDIA_TYPE
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.delivery import validate_delivery
from deepaha.p9b.models import ExtractionCandidate, SourceBundle, VerifiedFact
from deepaha.review.auth import ReviewerAuthenticationError, ReviewerRole
from tests.documents.test_docx_parser import _docx
from tests.integration.test_investigation_store import (
    StoreHarness,
    _collecting,
    _files,
    _pending,
    _review,
)
from tests.integration.test_investigation_store import (
    harness as original_harness,
)

harness = original_harness
pytestmark = pytest.mark.integration


def _with_extras(h: StoreHarness, extras: dict[str, tuple[str, bytes]]) -> tuple[UUID, str]:
    task_id, owner = _collecting(h)
    files, artifacts = _files(task_id)
    evidence = json.loads(files["evidence.json"])
    for name, (media, content) in extras.items():
        evidence["artifacts"].append(
            {
                "artifact_id": name,
                "source_url": f"https://example.gov/{name}",
                "local_path": f"artifacts/{name}",
                "remote_path": f"/workspace/task/artifacts/{name}",
                "file_name": name,
                "media_type": media,
                "sha256": sha256(content).hexdigest(),
            }
        )
        artifacts[name] = content
    files["evidence.json"] = json.dumps(evidence).encode()
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task_id, owner, files)
    h.store.finish(task_id, owner, delivery, files)
    return task_id, delivery.sha256


def test_mixed_formats_report_unsupported_and_failed_materials(harness: StoreHarness) -> None:
    h = harness
    fixtures = Path(__file__).parents[1] / "fixtures/documents"
    docx = _docx(
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Synthetic term</w:t></w:r></w:p></w:body></w:document>"
    )
    task_id, delivery_hash = _with_extras(
        h,
        {
            "terms.pdf": ("application/pdf", (fixtures / "minimal-text.pdf").read_bytes()),
            "positions.xlsx": (XLSX_MEDIA_TYPE, (fixtures / "minimal-table.xlsx").read_bytes()),
            "terms.docx": (DOCX_MEDIA_TYPE, docx),
            "legacy.doc": ("application/msword", b"synthetic unsupported legacy format"),
            "empty.pdf": ("application/pdf", (fixtures / "empty-text.pdf").read_bytes()),
        },
    )
    result = h.store.prepare_documents(task_id, delivery_hash, h.principal)
    preparation = result["document_preparation"]
    assert preparation["status"] == "NEEDS_ATTENTION"
    assert preparation["material_count"] == 6 and preparation["prepared_count"] == 4
    outcomes = {row["material_id"]: row for row in preparation["materials"]}
    assert outcomes["legacy.doc"]["outcome"] == "UNSUPPORTED"
    assert outcomes["legacy.doc"]["parse_attempt_id"] is None
    assert outcomes["empty.pdf"]["outcome"] == "FAILED"
    assert outcomes["empty.pdf"]["error_code"] == "READER_NO_TEXT"
    for name in ("notice", "terms.pdf", "positions.xlsx", "terms.docx"):
        assert outcomes[name]["outcome"] == "SUCCEEDED" and outcomes[name]["block_count"] > 0
    assert h.store.prepare_documents(task_id, delivery_hash, h.principal) == result


def test_interrupted_preparation_resumes_without_duplicate_versions(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery_hash = _with_extras(
        h, {"extra.html": ("text/html", b"<html><body><p>Additional term</p></body></html>")}
    )
    real_parse = DocumentService.parse
    calls = 0

    def interrupted(service: DocumentService, command: ParseDocumentCommand) -> ParseDocumentResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionError("synthetic interrupted preparation")
        return real_parse(service, command)

    with patch.object(DocumentService, "parse", interrupted), pytest.raises(ConnectionError):
        h.store.prepare_documents(task_id, delivery_hash, h.principal)
    partial = h.store.get(task_id)["document_preparation"]
    assert partial["prepared_count"] == 1 and partial["status"] == "NEEDS_ATTENTION"
    completed = h.store.prepare_documents(task_id, delivery_hash, h.principal)
    assert completed["document_preparation"]["prepared_count"] == 2
    with h.factory() as session:
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 2


def test_notice_json_prepares_once_without_approving_or_rewriting_delivery(
    harness: StoreHarness,
) -> None:
    content = json.dumps({"rows": [{"column13": "<p>Degree: doctorate.</p>"}]}).encode()
    task_id, delivery_hash = _with_extras(harness, {"notice.json": ("application/json", content)})
    before = harness.store.get(task_id)
    first = harness.store.prepare_documents(task_id, delivery_hash, harness.principal)
    assert harness.store.prepare_documents(task_id, delivery_hash, harness.principal) == first
    assert first["status"] == "PENDING_REVIEW" and first["review"] is None
    assert first["facts"] == before["facts"] and first["delivery_hash"] == delivery_hash
    row = next(
        row
        for row in first["document_preparation"]["materials"]
        if row["material_id"] == "notice.json"
    )
    assert row["outcome"] == "SUCCEEDED" and row["block_count"] > 0
    with harness.factory() as session:
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 2
        for forbidden in (SourceBundle, ExtractionCandidate, VerifiedFact):
            assert session.scalar(select(func.count()).select_from(forbidden)) == 0


def test_prepare_reuses_documents_and_preserves_frozen_candidate(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    before = h.store.get(task_id)
    assert before["document_preparation"]["status"] == "NOT_PREPARED"
    first = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    second = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    assert first == second == h.store.get(task_id)
    assert h.store.list_tasks()[0]["document_preparation"] is None
    assert first["status"] == "PENDING_REVIEW" and first["review"] is None
    assert first["facts"] == before["facts"] and first["delivery_hash"] == delivery.sha256
    preparation = first["document_preparation"]
    assert preparation["status"] == "PREPARED"
    assert preparation["scope"] == "DOCUMENT_EVIDENCE_ONLY"
    assert preparation["material_count"] == preparation["prepared_count"] == 1
    assert preparation["materials"][0]["block_count"] >= 1
    with h.factory() as session:
        for model in (Document, ParseAttempt):
            assert session.scalar(select(func.count()).select_from(model)) == 1
        block = session.scalar(select(DocumentBlock))
        assert block is not None and "Degree: doctorate." in block.canonical_text_or_value
        assert session.get(EvidenceRef, block.evidence_ref_id) is not None
        for forbidden in (SourceBundle, ExtractionCandidate, VerifiedFact):
            assert session.scalar(select(func.count()).select_from(forbidden)) == 0


def test_configured_doc_reader_prepares_without_approving_original_material(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPAHA_DOC_READER_IMAGE", "sha256:" + "1" * 64)
    content = bytes.fromhex("d0cf11e0a1b11ae1") + bytes(504)
    task_id, delivery_hash = _with_extras(harness, {"guide.doc": ("application/msword", content)})
    with patch(
        "deepaha.evidence_verification.adapters.legacy_doc.convert_doc",
        return_value=b"<book><chapter><para>Read the official guide.</para></chapter></book>",
    ):
        result = harness.store.prepare_documents(task_id, delivery_hash, harness.principal)
        assert result["document_preparation"]["status"] == "PREPARED"
        assert result["status"] == "PENDING_REVIEW" and result["review"] is None
        assert result["delivery_hash"] == delivery_hash
        assert harness.store.prepare_documents(task_id, delivery_hash, harness.principal) == result


def test_preparation_rejects_stale_hash_before_any_parse(harness: StoreHarness) -> None:
    h = harness
    task_id, _, _ = _pending(h)
    with pytest.raises(InvestigationError, match="DOCUMENT_DELIVERY_CONFLICT"):
        h.store.prepare_documents(task_id, "0" * 64, h.principal)
    with h.factory() as session:
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 0


def test_rejected_materials_cannot_be_prepared(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    command = _review(delivery).model_copy(update={"decision": "REJECT"})
    h.store.review(task_id, command, h.principal, "reject-synthetic-materials")
    with pytest.raises(InvestigationError, match="DOCUMENT_DELIVERY_CONFLICT"):
        h.store.prepare_documents(task_id, delivery.sha256, h.principal)


def test_preparation_requires_operator_role(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    reviewer = replace(h.principal, roles=frozenset({ReviewerRole.VALIDATION_REVIEWER}))
    with pytest.raises(ReviewerAuthenticationError):
        h.store.prepare_documents(task_id, delivery.sha256, reviewer)


def test_preparation_rechecks_bytes_even_after_prior_success(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    with (
        patch.object(h.objects, "get_bytes", return_value=b"changed"),
        pytest.raises(InvestigationError, match="STORED_MATERIAL_INTEGRITY_FAILED"),
    ):
        h.store.prepare_documents(task_id, delivery.sha256, h.principal)


def test_concurrent_preparation_has_one_document_version(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: h.store.prepare_documents(task_id, delivery.sha256, h.principal), range(2)
            )
        )
    assert results[0] == results[1]
    with h.factory() as session:
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 1
