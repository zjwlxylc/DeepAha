"""Synthetic registration receipts prove atomicity, never independent truth."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, NoReturn
from uuid import UUID

import pytest
from sqlalchemy import select

from deepaha.documents.models import DocumentBlock, EvidenceRef
from deepaha.investigations.contracts import (
    InvestigationError,
    RegisterInvestigationIdentity,
    RegisterInvestigationPositions,
)
from deepaha.investigations.delivery import ValidatedDelivery
from deepaha.investigations.models import InvestigationBinding
from deepaha.investigations.registration import register_identity, register_positions
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.models import OpportunityUnit, SourceBundleRevision, VerifiedFact
from tests.integration.test_investigation_store import (
    StoreHarness,
    _count,
    _pending,
    _review,
    harness,
)

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def _ready(h: StoreHarness) -> tuple[UUID, ValidatedDelivery]:
    task, delivery, _ = _pending(h)
    h.store.prepare_documents(task, delivery.sha256, h.principal)
    h.store.review(task, _review(delivery), h.principal, "synthetic-intake")
    return task, delivery


def _command(delivery: ValidatedDelivery, **extra: object) -> RegisterInvestigationIdentity:
    return RegisterInvestigationIdentity.model_validate(
        {
            "delivery_hash": delivery.sha256,
            "canonical_title": "Synthetic notice",
            "type": "PUBLIC_INSTITUTION_JOB",
            "issuer_name": "Synthetic issuer",
            "reason": "Synthetic identity review, not field approval",
            **extra,
        }
    )


def test_registration_is_internal_pending_and_replayable(harness: StoreHarness) -> None:
    h = harness
    task, delivery = _ready(h)
    original = h.store.get(task)
    command = _command(
        delivery,
        positions=[
            {
                "entity_id": "position",
                "unit_key": "A-01",
                "label": "Synthetic post",
            }
        ],
    )
    result = register_identity(h.store, task, command, h.principal, "new-identity")
    binding = result["entity_binding"]
    assert binding["unmapped_position_ids"] == []
    replay = register_identity(h.store, task, command, h.principal, "new-identity")
    assert replay["binding_receipt"] == binding
    with h.factory() as session:
        opp = session.get(Opportunity, UUID(binding["opportunity_id"]))
        assert opp is not None
        version = session.get(OpportunityVersion, (opp.opportunity_id, 1))
        assert version is not None
        assert opp.publication_status == "INTERNAL"
        assert opp.status == "UNKNOWN"
        assert version.review_status == "PENDING"
        assert version.snapshot["published_at"] is None
        window = version.snapshot["application_window"]
        assert isinstance(window, dict) and window["closes_on"] is None
        unit = session.scalar(select(OpportunityUnit))
        assert unit is not None
        assert unit.public_id.startswith("unit_") and unit.public_id != "position"
        assert _count(session, VerifiedFact) == 0
        assert _count(session, Opportunity) == 1
        assert (
            session.scalar(
                select(DocumentBlock).where(DocumentBlock.block_type == "READER_TEXT_SPAN")
            )
            is not None
        )
        assert (
            session.scalar(select(EvidenceRef).where(EvidenceRef.locator_schema_version == "0.9.0"))
            is not None
        )
    current = h.store.get(task)
    for key in ("delivery_hash", "facts", "opportunities", "evidence_check"):
        assert current[key] == original[key]
    with pytest.raises(InvestigationError, match="IDEMPOTENCY_CONFLICT"):
        register_identity(
            h.store, task, _command(delivery, reason="Changed"), h.principal, "new-identity"
        )


def test_bad_position_rolls_back_new_identity_and_bundle(harness: StoreHarness) -> None:
    h = harness
    task, delivery = _ready(h)
    with pytest.raises(InvestigationError, match="REGISTRATION_POSITION_INVALID"):
        register_identity(
            h.store,
            task,
            _command(
                delivery,
                positions=[
                    {
                        "entity_id": "unit",
                        "unit_key": "group",
                        "label": "An organization is not a post",
                    }
                ],
            ),
            h.principal,
            "bad-group",
        )
    with h.factory() as session:
        for model in (Opportunity, SourceBundleRevision, OpportunityUnit):
            assert _count(session, model) == 0


def test_add_positions_preserves_opportunity_and_rejects_stale_revision(
    harness: StoreHarness,
) -> None:
    h = harness
    task, delivery = _ready(h)
    first = register_identity(h.store, task, _command(delivery), h.principal, "identity")[
        "entity_binding"
    ]
    command = RegisterInvestigationPositions.model_validate(
        {
            "delivery_hash": delivery.sha256,
            "previous_binding_id": first["binding_id"],
            "reason": "Synthetic post identity",
            "positions": [
                {
                    "entity_id": "position",
                    "unit_key": "A-01",
                    "label": "Synthetic post",
                }
            ],
        }
    )
    result = register_positions(h.store, task, command, h.principal, "post")
    assert result["entity_binding"]["opportunity_id"] == first["opportunity_id"]
    assert result["entity_binding"]["sequence"] == 2
    assert len(result["entity_binding"]["positions"]) == 1
    assert (
        register_positions(h.store, task, command, h.principal, "post")["binding_receipt"]
        == result["entity_binding"]
    )
    with pytest.raises(InvestigationError, match="BINDING_REVISION_CONFLICT"):
        register_positions(h.store, task, command, h.principal, "stale-post")


def test_registration_requires_approved_intake(harness: StoreHarness) -> None:
    h = harness
    task, delivery, _ = _pending(h)
    h.store.prepare_documents(task, delivery.sha256, h.principal)
    with pytest.raises(InvestigationError, match="BINDING_DELIVERY_CONFLICT"):
        register_identity(h.store, task, _command(delivery), h.principal, "unapproved")


def test_failure_after_creating_identity_rolls_back_every_record(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.p9b.identity import OpportunityUnitService, UnitIdentityCollision

    h = harness
    task, delivery = _ready(h)

    def fail(*args: object, **kwargs: object) -> NoReturn:
        raise UnitIdentityCollision("synthetic collision after bundle freeze")

    monkeypatch.setattr(OpportunityUnitService, "create_unit", fail)
    with pytest.raises(InvestigationError, match="REGISTRATION_POSITION_KEY_CONFLICT"):
        register_identity(
            h.store,
            task,
            _command(
                delivery,
                positions=[
                    {
                        "entity_id": "position",
                        "unit_key": "A-01",
                        "label": "Synthetic post",
                    }
                ],
            ),
            h.principal,
            "failure",
        )
    with h.factory() as session:
        for model in (
            Opportunity,
            OpportunityVersion,
            SourceBundleRevision,
            OpportunityUnit,
            InvestigationBinding,
        ):
            assert _count(session, model) == 0


@pytest.mark.parametrize("different_url", [False, True])
def test_already_resolved_document_cannot_be_registered_again(
    harness: StoreHarness, different_url: bool
) -> None:
    from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
    from deepaha.contracts.phase2 import OpportunityTypeV02
    from deepaha.contracts.phase3 import OpportunityDocumentRole
    from deepaha.investigations.bindings import _validated_members
    from deepaha.opportunities.service import OpportunityResolutionService
    from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument

    h = harness
    task_id, delivery = _ready(h)
    with h.factory.begin() as session:
        task = h.store._get(session, task_id)
        member = _validated_members(h.store, session, task)[0]
        assert member.evidence_ref_id is not None
        result = OpportunityResolutionService(
            session_factory=h.factory, clock=h.store.clock
        ).resolve_in_session(
            session,
            ResolutionDocument(
                document_id=member.document_id,
                source_id=h.command.source_id,
                source_tier=SourceTier.OFFICIAL_PRIMARY,
                evidence_ref_id=member.evidence_ref_id,
                role=OpportunityDocumentRole.PRIMARY_NOTICE,
                canonical_url=h.command.notice_url + ("/other" if different_url else ""),
                external_id=None,
                references_document_ids=(),
                effective_at=h.store.clock(),
                facts=OpportunityPatch(
                    canonical_title="Existing title",
                    type=OpportunityTypeV02.PUBLIC_INSTITUTION_JOB,
                    issuer_name="Existing issuer",
                    status=OpportunityStatus.UNKNOWN,
                ),
            ),
        )
        identity = result.opportunity_id
    with pytest.raises(
        InvestigationError, match="REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED"
    ):
        register_identity(h.store, task_id, _command(delivery), h.principal, "duplicate")
    with h.factory() as session:
        assert _count(session, Opportunity) == 1
        existing = session.get(Opportunity, identity)
        assert existing is not None and existing.canonical_title == "Existing title"
        assert _count(session, InvestigationBinding) == 0


def test_unknown_jurisdiction_does_not_hide_possible_duplicate(harness: StoreHarness) -> None:
    from tests.integration.test_investigation_binding import _target

    h = harness
    task, delivery = _ready(h)
    identity = _target(h)
    with h.factory.begin() as session:
        opportunity = session.get(Opportunity, identity)
        assert opportunity is not None
        opportunity.canonical_title = "Synthetic notice"
        opportunity.issuer_name = "Synthetic issuer"
        opportunity.jurisdiction = "浙江"
    with pytest.raises(
        InvestigationError, match="REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED"
    ):
        register_identity(h.store, task, _command(delivery), h.principal, "possible-duplicate")
    with h.factory() as session:
        assert _count(session, Opportunity) == 1
        assert _count(session, InvestigationBinding) == 0


def test_parallel_replay_creates_only_one_identity(harness: StoreHarness) -> None:
    h = harness
    task, delivery = _ready(h)

    def register(_: int) -> dict[str, Any]:
        result = register_identity(h.store, task, _command(delivery), h.principal, "double-click")
        receipt: dict[str, Any] = result["binding_receipt"]
        return receipt

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(register, range(2)))
    assert first == second
    with h.factory() as session:
        assert _count(session, Opportunity) == 1
        assert _count(session, InvestigationBinding) == 1


@pytest.mark.parametrize("change", ["inactive", "synthetic", "purpose", "role"])
def test_registration_rechecks_current_human_account(harness: StoreHarness, change: str) -> None:
    from deepaha.local_human_test.review import HumanReviewError
    from deepaha.review.models import ReviewerAccountModel

    h = harness
    task, delivery = _ready(h)
    with h.factory.begin() as session:
        account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
        assert account is not None
        if change == "inactive":
            account.active = False
        if change == "synthetic":
            account.synthetic = True
        if change == "purpose":
            account.allowed_purposes = ["FEEDBACK_REVIEW_AND_VALIDATION"]
        if change == "role":
            account.roles = ["LOCAL_TEST_OPERATOR"]
    with pytest.raises((InvestigationError, HumanReviewError)):
        register_identity(h.store, task, _command(delivery), h.principal, "no-authority")
