import re
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid7

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase8 import (
    DeadlineChangeReminderIntentSchemaV07,
    TestInboxEntrySchemaV07,
)
from deepaha.notifications.models import TestInboxEntryModel
from deepaha.opportunities.models import Opportunity
from deepaha.public_catalog.service import PublicCatalogService

ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class DeliveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        if ERROR_CODE_PATTERN.fullmatch(code) is None:
            raise ValueError("delivery error code must be a bounded stable code")
        self.code = code
        super().__init__(code)


class TransientDeliveryError(DeliveryError):
    pass


class PermanentDeliveryError(DeliveryError):
    pass


def _entry_contract(row: TestInboxEntryModel) -> TestInboxEntrySchemaV07:
    return TestInboxEntrySchemaV07.model_validate(
        {
            "inbox_entry_id": row.inbox_entry_id,
            "reminder_id": row.reminder_id,
            "user_id": row.user_id,
            "opportunity_id": row.opportunity_id,
            "opportunity_public_id": row.opportunity_public_id,
            "opportunity_title": row.opportunity_title,
            "event_id": row.event_id,
            "from_version": row.from_version,
            "to_version": row.to_version,
            "old_closes_on": row.old_closes_on,
            "new_closes_on": row.new_closes_on,
            "direction": row.direction,
            "previous_evidence_ref_id": row.previous_evidence_ref_id,
            "current_evidence_ref_id": row.current_evidence_ref_id,
            "previous_official_url": row.previous_official_url,
            "current_official_url": row.current_official_url,
            "personal_detail_path": row.personal_detail_path,
            "detected_at": row.detected_at,
            "delivered_at": row.delivered_at,
            "target": row.target,
            "contract_version": row.contract_version,
        }
    )


class PostgresTestInboxAdapter:
    def __init__(self, *, id_factory: Callable[[], UUID] = uuid7) -> None:
        self._id_factory = id_factory

    def deliver(
        self,
        session: Session,
        intent: DeadlineChangeReminderIntentSchemaV07,
        *,
        delivered_at: datetime,
    ) -> TestInboxEntrySchemaV07:
        existing = session.scalar(
            select(TestInboxEntryModel).where(TestInboxEntryModel.reminder_id == intent.reminder_id)
        )

        opportunity = session.get(Opportunity, intent.opportunity_id)
        if opportunity is None:
            raise PermanentDeliveryError("OPPORTUNITY_BINDING_MISSING")
        detail = PublicCatalogService(session).get_opportunity(opportunity.public_id)
        if detail is None or detail.current_version != intent.to_version:
            raise PermanentDeliveryError("PUBLIC_BINDING_UNAVAILABLE")

        evidence_urls = {
            item.evidence_ref_id: str(item.official_url) for item in detail.key_evidence
        }
        evidence_urls.update(
            {item.evidence_ref_id: str(item.official_url) for item in detail.history}
        )
        previous_url = evidence_urls.get(intent.previous_evidence_ref_id)
        current_url = evidence_urls.get(intent.current_evidence_ref_id)
        if previous_url is None or current_url is None:
            raise PermanentDeliveryError("OFFICIAL_EVIDENCE_BINDING_MISSING")

        try:
            contract = TestInboxEntrySchemaV07.model_validate(
                {
                    "inbox_entry_id": (
                        existing.inbox_entry_id if existing is not None else self._id_factory()
                    ),
                    "reminder_id": intent.reminder_id,
                    "user_id": intent.user_id,
                    "opportunity_id": intent.opportunity_id,
                    "opportunity_public_id": detail.public_id,
                    "opportunity_title": detail.title,
                    "event_id": intent.event_id,
                    "from_version": intent.from_version,
                    "to_version": intent.to_version,
                    "old_closes_on": intent.old_closes_on,
                    "new_closes_on": intent.new_closes_on,
                    "direction": intent.direction,
                    "previous_evidence_ref_id": intent.previous_evidence_ref_id,
                    "current_evidence_ref_id": intent.current_evidence_ref_id,
                    "previous_official_url": previous_url,
                    "current_official_url": current_url,
                    "personal_detail_path": f"/me/opportunities/{detail.public_id}",
                    "detected_at": intent.detected_at,
                    "delivered_at": (
                        existing.delivered_at if existing is not None else delivered_at
                    ),
                    "target": intent.target,
                    "contract_version": intent.contract_version,
                }
            )
        except ValidationError as error:
            raise PermanentDeliveryError("TEST_INBOX_CONTRACT_INVALID") from error
        if existing is not None:
            try:
                persisted = _entry_contract(existing)
            except ValidationError as error:
                raise PermanentDeliveryError("TEST_INBOX_REPLAY_INVALID") from error
            if persisted != contract:
                raise PermanentDeliveryError("TEST_INBOX_REPLAY_MISMATCH")
            return persisted
        session.add(
            TestInboxEntryModel(
                inbox_entry_id=contract.inbox_entry_id,
                reminder_id=contract.reminder_id,
                user_id=contract.user_id,
                opportunity_id=contract.opportunity_id,
                opportunity_public_id=contract.opportunity_public_id,
                opportunity_title=contract.opportunity_title,
                event_id=contract.event_id,
                from_version=contract.from_version,
                to_version=contract.to_version,
                old_closes_on=contract.old_closes_on,
                new_closes_on=contract.new_closes_on,
                direction=contract.direction.value,
                previous_evidence_ref_id=contract.previous_evidence_ref_id,
                current_evidence_ref_id=contract.current_evidence_ref_id,
                previous_official_url=str(contract.previous_official_url),
                current_official_url=str(contract.current_official_url),
                personal_detail_path=contract.personal_detail_path,
                detected_at=contract.detected_at,
                delivered_at=contract.delivered_at,
                target=contract.target.value,
                contract_version=contract.contract_version,
            )
        )
        session.flush()
        return contract


__all__ = [
    "PermanentDeliveryError",
    "PostgresTestInboxAdapter",
    "TransientDeliveryError",
]
