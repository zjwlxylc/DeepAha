"""Offline check receipts preserve originals and never approve field facts."""

import json
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
from uuid import UUID, uuid7

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.documents.models import EvidenceRef
from deepaha.investigations.contracts import digest
from deepaha.investigations.delivery import validate_delivery
from deepaha.investigations.models import InvestigationEvidenceCheck, InvestigationTask
from deepaha.p9b.models import VerifiedFact
from tests.integration.test_investigation_store import (
    StoreHarness,
    _collecting,
    _files,
    _pending,
    harness,
)

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_raw_file_anchor_added_by_binding_does_not_change_reader_receipt(
    harness: StoreHarness,
) -> None:
    from deepaha.investigations.evidence_checks import evaluate_check
    from deepaha.investigations.models import InvestigationMaterial
    from deepaha.investigations.registration import register_identity
    from tests.integration.test_investigation_registration import _command, _ready

    h = harness
    task_id, delivery = _ready(h)
    before = h.store.get(task_id)["evidence_check"]
    register_identity(h.store, task_id, _command(delivery), h.principal, "new-identity")
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None
        materials = list(
            session.scalars(
                select(InvestigationMaterial)
                .where(InvestigationMaterial.task_id == task_id)
                .order_by(InvestigationMaterial.material_id)
            )
        )
        current = evaluate_check(session, h.store.objects, task, materials)
    assert current["inputs"] == before["inputs"]
    assert digest(current) == before["result_hash"]


def test_read_only_evaluation_replays_the_exact_persisted_receipt(harness: StoreHarness) -> None:
    from deepaha.investigations.evidence_checks import evaluate_check
    from deepaha.investigations.models import InvestigationMaterial

    h = harness
    task_id, delivery, _ = _pending(h)
    h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    with h.factory.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        task = session.get(InvestigationTask, task_id)
        receipt = session.scalar(select(InvestigationEvidenceCheck))
        assert task is not None and receipt is not None
        materials = list(
            session.scalars(
                select(InvestigationMaterial)
                .where(InvestigationMaterial.task_id == task_id)
                .order_by(InvestigationMaterial.material_id)
            )
        )
        payload = evaluate_check(session, h.store.objects, task, materials)
        assert digest(payload) == receipt.result_hash
        assert json.loads(json.dumps(payload)) == receipt.payload


def test_check_is_bound_idempotent_and_does_not_rewrite_delivery(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None
        original = task.delivery
    before = h.store.get(task_id)
    assert before.get("evidence_check") is None
    first = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    check = first["evidence_check"]
    assert check["verdict"] == "PASS"
    assert check["counts"] == {"PASS": 1, "FAIL": 0, "UNVERIFIED": 0}
    row = check["references"][0]
    assert row["verification"]["content_support"] == "FOUND"
    assert row["verification"]["declared_locator"] == "VERIFIED"
    assert row["verification"]["original_locator"] == {"selector": "#terms"}
    assert check["inputs"]["verifier_version"] == row["verification"]["verifier_version"]
    assert row["persistent_binding"]["evidence_ref_id"]
    assert h.store.prepare_documents(task_id, delivery.sha256, h.principal) == first
    assert len(first["evidence_check_history"]) == 1
    assert h.store.list_tasks()[0]["evidence_check"] is None
    with h.factory() as session:
        task = session.get(InvestigationTask, task_id)
        assert task is not None and task.delivery == original
        assert session.get(EvidenceRef, UUID(row["persistent_binding"]["evidence_ref_id"]))
        assert session.scalar(select(func.count()).select_from(VerifiedFact)) == 0
    assert first["review"] is None and first["facts"] == before["facts"]


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_check_receipt_cannot_be_changed(harness: StoreHarness, operation: str) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    statement = (
        "UPDATE investigation_evidence_checks SET payload = '{}'::jsonb"
        if operation == "UPDATE"
        else "DELETE FROM investigation_evidence_checks"
    )
    with h.factory.begin() as session, pytest.raises(DBAPIError, match="immutable"):
        session.execute(text(statement))


def test_new_check_version_appends_and_unsupported_word_stays_unverified(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, owner = _collecting(h)
    files, artifacts = _files(task_id)
    evidence = json.loads(files["evidence.json"])
    artifacts["notice"] = b"Synthetic binary Word placeholder; no registered reader"
    evidence["artifacts"][0].update(
        media_type="application/msword", sha256=sha256(artifacts["notice"]).hexdigest()
    )
    files["evidence.json"] = json.dumps(evidence).encode()
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task_id, owner, files)
    h.store.finish(task_id, owner, delivery, files)
    first = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    check = first["evidence_check"]
    assert check["counts"] == {"PASS": 0, "FAIL": 0, "UNVERIFIED": 1}
    assert check["verdict"] == "UNVERIFIED"
    assert check["references"][0]["persistent_binding"] is None
    with patch("deepaha.investigations.evidence_checks.CHECK_VERSION", "synthetic-version/2"):
        second = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    assert second["evidence_check"]["check_id"] != check["check_id"]
    assert second["evidence_check_history"][1] == check
    assert second["facts"] == first["facts"]
    with h.factory() as session:
        assert session.scalar(select(func.count()).select_from(InvestigationEvidenceCheck)) == 2


def test_db_rejects_self_consistent_receipt_without_actual_evidence(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    payload = {
        "inputs": {"delivery_hash": delivery.sha256},
        "scope": "MECHANICAL_EVIDENCE_ONLY",
        "verdict": "PASS",
        "counts": {"PASS": 1, "FAIL": 0, "UNVERIFIED": 0},
        "references": [],
    }
    with (
        h.factory.begin() as session,
        pytest.raises(DBAPIError, match="Invalid investigation evidence check"),
    ):
        session.add(
            InvestigationEvidenceCheck(
                check_id=uuid7(),
                task_id=task_id,
                delivery_hash=delivery.sha256,
                input_hash=digest(payload["inputs"]),
                result_hash=digest(payload),
                payload=payload,
                checked_by=h.principal.reviewer_id,
                created_at=h.clock(),
            )
        )
        session.flush()


@pytest.mark.parametrize("change", ["counts", "quote", "index", "binding", "materials"])
def test_db_checks_receipt_semantics_even_with_matching_hashes(
    harness: StoreHarness, change: str
) -> None:
    h = harness
    task_id, delivery, _ = _pending(h)
    h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    with h.factory() as session:
        original = session.scalar(select(InvestigationEvidenceCheck))
        assert original is not None
        payload = deepcopy(original.payload)
    # JSON typing here mirrors a storage-level compatibility test, not an API.
    candidate = json.loads(json.dumps(payload))
    candidate["inputs"]["check_version"] = "synthetic-new-version"
    if change == "counts":
        candidate["counts"]["PASS"] = 900
    elif change == "quote":
        candidate["references"][0]["verification"]["quote"] = "Changed text"
    elif change == "index":
        candidate["references"][0]["reference_index"] = 3
    elif change == "materials":
        candidate["inputs"]["materials"] = []
    else:
        candidate["references"][0]["persistent_binding"]["evidence_ref_id"] = str(uuid7())
    with (
        h.factory.begin() as session,
        pytest.raises(DBAPIError, match="Invalid investigation evidence check"),
    ):
        session.add(
            InvestigationEvidenceCheck(
                check_id=uuid7(),
                task_id=task_id,
                delivery_hash=delivery.sha256,
                input_hash=digest(candidate["inputs"]),
                result_hash=digest(candidate),
                payload=candidate,
                checked_by=h.principal.reviewer_id,
                created_at=h.clock(),
            )
        )
        session.flush()


def test_receipt_history_blocks_downgrade(harness: StoreHarness) -> None:
    from alembic import command
    from alembic.config import Config

    h = harness
    task_id, delivery, _ = _pending(h)
    before = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    with pytest.raises(RuntimeError, match="Cannot discard investigation evidence check history"):
        command.downgrade(Config("alembic.ini"), "20260908_0038")
    assert h.store.get(task_id) == before
