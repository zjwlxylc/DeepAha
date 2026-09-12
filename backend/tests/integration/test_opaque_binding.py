"""An excluded, parser-less material must still reach a frozen bundle -- as a whole file."""

from uuid import UUID

import pytest
from sqlalchemy import select

from deepaha.documents.models import DocumentBlock, EvidenceRef
from deepaha.investigations.contracts import BindInvestigation, ReviewInvestigation
from deepaha.investigations.document_exclusions import exclude_document
from deepaha.investigations.models import InvestigationMaterial
from deepaha.p9b.models import SourceBundleMember
from tests.integration.test_investigation_binding import _target
from tests.integration.test_investigation_documents import _with_extras
from tests.integration.test_investigation_store import StoreHarness
from tests.integration.test_investigation_store import harness as original_harness

harness = original_harness
pytestmark = pytest.mark.integration

LEGACY_CONTENT = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00synthetic-legacy-msword-body"
LEGACY_MATERIAL = "legacy.doc"
EXCLUSION_REASON = "Legacy OLE2 .doc has no registered parser in this deployment."


def _bind_command(delivery_hash: str, identity: UUID) -> BindInvestigation:
    return BindInvestigation(
        delivery_hash=delivery_hash,
        opportunity_id=identity,
        opportunity_version=1,
        reason="Synthetic association of a bundle that contains an excluded material",
    )


def _approval(delivery_hash: str) -> ReviewInvestigation:
    return ReviewInvestigation(
        decision="APPROVE",
        delivery_hash=delivery_hash,
        reason="Synthetic intake approval of a delivery containing an excluded material",
    )


def test_excluded_material_binds_as_a_whole_file_member_only(harness: StoreHarness) -> None:
    h = harness
    task_id, delivery_hash = _with_extras(
        h, {LEGACY_MATERIAL: ("application/msword", LEGACY_CONTENT)}
    )

    excluded = exclude_document(
        h.store, task_id, delivery_hash, LEGACY_MATERIAL, EXCLUSION_REASON, h.principal
    )
    rows = {row["material_id"]: row for row in excluded["document_preparation"]["materials"]}
    assert rows[LEGACY_MATERIAL]["excluded"] is True
    # Written exclusion alone is not evidence: the mode stays null until the opaque block
    # really exists, so a reviewer can never cite an excluded file that was not parsed.
    assert rows[LEGACY_MATERIAL]["evidence_mode"] is None

    prepared = h.store.prepare_documents(task_id, delivery_hash, h.principal)
    preparation = prepared["document_preparation"]
    assert preparation["status"] == "PREPARED"
    assert preparation["excluded_count"] == 1
    rows = {row["material_id"]: row for row in preparation["materials"]}
    assert rows[LEGACY_MATERIAL]["outcome"] == "SUCCEEDED"
    assert rows[LEGACY_MATERIAL]["block_count"] == 1
    assert rows[LEGACY_MATERIAL]["evidence_mode"] == "OPAQUE_NO_TEXT"
    assert rows[LEGACY_MATERIAL]["document_id"] is not None

    h.store.review(task_id, _approval(delivery_hash), h.principal, "approve-excluded")
    result = h.store.bind(
        task_id, _bind_command(delivery_hash, _target(h)), h.principal, "bind-excluded"
    )
    assert result["entity_binding"]["bundle_status"] == "FROZEN"

    with h.factory() as session:
        materials = list(
            session.scalars(
                select(InvestigationMaterial).where(InvestigationMaterial.task_id == task_id)
            )
        )
        members = list(session.scalars(select(SourceBundleMember)))
        # 0037 forbids a bundle whose member count differs from the material count.
        assert len(members) == len(materials) == 2
        assert {member.wma_material_id for member in members} == {"notice", LEGACY_MATERIAL}
        for member in members:
            ref = session.get(EvidenceRef, member.evidence_ref_id)
            assert ref is not None
            assert ref.locator_kind == "full_document"
            assert ref.locator_value == "*"
            assert ref.locator_schema_version == "0.1.0"
        # The opaque block keeps its own text-free citation, which no member may anchor on.
        opaque_ref = session.scalar(
            select(EvidenceRef).where(EvidenceRef.locator_kind == "opaque_whole_file")
        )
        assert opaque_ref is not None
        assert opaque_ref.evidence_ref_id not in {member.evidence_ref_id for member in members}
        block = session.scalar(
            select(DocumentBlock).where(DocumentBlock.block_type == "OPAQUE_BINARY")
        )
        assert block is not None
        assert block.canonical_text_or_value == ""
        assert block.document_id in {member.document_id for member in members}


def test_revoked_exclusion_restores_the_text_requirement_and_blocks_binding(
    harness: StoreHarness,
) -> None:
    """Revoking after an opaque parse must not silently keep the bundle bindable forever."""
    from deepaha.investigations.contracts import InvestigationError
    from deepaha.investigations.document_exclusions import revoke_exclusion

    h = harness
    task_id, delivery_hash = _with_extras(
        h, {LEGACY_MATERIAL: ("application/msword", LEGACY_CONTENT)}
    )
    exclude_document(
        h.store, task_id, delivery_hash, LEGACY_MATERIAL, EXCLUSION_REASON, h.principal
    )
    h.store.prepare_documents(task_id, delivery_hash, h.principal)
    revoke_exclusion(
        h.store,
        task_id,
        delivery_hash,
        LEGACY_MATERIAL,
        "Parser coverage changed; the material must yield real text again.",
        h.principal,
    )
    preparation = h.store.get(task_id)["document_preparation"]
    assert preparation["status"] == "NEEDS_ATTENTION"
    rows = {row["material_id"]: row for row in preparation["materials"]}
    assert rows[LEGACY_MATERIAL]["outcome"] == "UNSUPPORTED"
    assert rows[LEGACY_MATERIAL]["excluded"] is False
    h.store.review(task_id, _approval(delivery_hash), h.principal, "approve-revoked")
    with pytest.raises(InvestigationError, match="BINDING_DOCUMENTS_NOT_READY"):
        h.store.bind(task_id, _bind_command(delivery_hash, _target(h)), h.principal, "bind-revoked")
