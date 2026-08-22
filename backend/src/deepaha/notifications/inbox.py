from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase8 import TestInboxEntrySchemaV07
from deepaha.notifications.models import TestInboxEntryModel
from deepaha.notifications.schemas import ReminderInboxPage
from deepaha.personal.auth import Principal


def _owner_inbox_statement(
    owner_id: UUID,
    *,
    limit: int,
) -> Select[tuple[TestInboxEntryModel]]:
    if not 1 <= limit <= 50:
        raise ValueError("inbox limit must be between 1 and 50")
    return (
        select(TestInboxEntryModel)
        .where(TestInboxEntryModel.user_id == owner_id)
        .order_by(
            TestInboxEntryModel.delivered_at.desc(),
            TestInboxEntryModel.inbox_entry_id.desc(),
        )
        .limit(limit)
    )


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


class ReminderInboxService:
    def __init__(self, *, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_for_owner(
        self,
        principal: Principal,
        *,
        limit: int = 50,
    ) -> ReminderInboxPage:
        statement = _owner_inbox_statement(principal.user_id, limit=limit)
        with self._session_factory() as session:
            items = tuple(_entry_contract(row) for row in session.scalars(statement))
        return ReminderInboxPage(items=items, count=len(items))


__all__ = ["ReminderInboxService"]
