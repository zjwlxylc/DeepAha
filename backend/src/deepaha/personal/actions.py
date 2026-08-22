import json
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase6 import (
    ActionEventType,
    ActionState,
    MaterialPlanItemSchemaV05,
    PersonalActionEventSchemaV05,
    PersonalActionSnapshotSchemaV05,
    UserDataPurpose,
)
from deepaha.opportunities.models import Opportunity
from deepaha.personal.auth import Principal
from deepaha.personal.models import (
    PersonalActionEventModel,
    PersonalActionSnapshotModel,
    PersonalIdempotencyRecordModel,
)
from deepaha.personal.profile import (
    IdempotencyConflict,
    ProfileService,
    idempotency_key_sha256,
)
from deepaha.personal.schemas import MaterialPlanItemWrite, OfficialLinkResult
from deepaha.public_catalog.schemas import PublicOpportunityDetail
from deepaha.public_catalog.service import PublicCatalogService

type ActionValues = tuple[
    bool,
    ActionState,
    tuple[MaterialPlanItemSchemaV05, ...],
]
type ActionMutation = Callable[
    [bool, ActionState, tuple[MaterialPlanItemSchemaV05, ...]],
    ActionValues,
]


class ActionUnavailable(ValueError):
    pass


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class ActionService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        profile_service: ProfileService,
        id_factory: Callable[[], UUID] = uuid7,
        now_factory: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._profile_service = profile_service
        self._id_factory = id_factory
        self._now_factory = now_factory

    def get_current(
        self,
        principal: Principal,
        public_id: str,
    ) -> PersonalActionSnapshotSchemaV05 | None:
        if not self._action_tracking_allowed(principal):
            return None
        with self._session_factory() as session:
            opportunity = session.scalar(
                select(Opportunity).where(Opportunity.public_id == public_id)
            )
            if opportunity is None:
                return None
            row = self._current_row(session, principal.user_id, opportunity.opportunity_id)
            return None if row is None else self._snapshot_contract(row)

    def set_saved(
        self,
        principal: Principal,
        public_id: str,
        saved: bool,
        *,
        idempotency_key: str,
    ) -> PersonalActionSnapshotSchemaV05:
        result = self._write(
            principal,
            public_id,
            operation="ACTION_SAVED",
            event_type=ActionEventType.SAVED_CHANGED,
            payload={"saved": saved},
            idempotency_key=idempotency_key,
            mutation=lambda _saved, state, items: (saved, state, items),
            record_noop=False,
        )
        return result.action

    def set_status(
        self,
        principal: Principal,
        public_id: str,
        state: ActionState,
        *,
        idempotency_key: str,
    ) -> PersonalActionSnapshotSchemaV05:
        result = self._write(
            principal,
            public_id,
            operation="ACTION_STATUS",
            event_type=ActionEventType.ACTION_STATE_CHANGED,
            payload={"state": state.value},
            idempotency_key=idempotency_key,
            mutation=lambda saved, _state, items: (saved, state, items),
            record_noop=False,
        )
        return result.action

    def set_material_plan(
        self,
        principal: Principal,
        public_id: str,
        items: tuple[MaterialPlanItemWrite, ...],
        *,
        idempotency_key: str,
    ) -> PersonalActionSnapshotSchemaV05:
        material_items = tuple(
            MaterialPlanItemSchemaV05.model_validate(item.model_dump()) for item in items
        )
        result = self._write(
            principal,
            public_id,
            operation="ACTION_MATERIALS",
            event_type=ActionEventType.MATERIAL_PLAN_CHANGED,
            payload={"items": [item.model_dump(mode="json") for item in material_items]},
            idempotency_key=idempotency_key,
            mutation=lambda saved, state, _items: (saved, state, material_items),
            record_noop=False,
        )
        return result.action

    def record_official_link(
        self,
        principal: Principal,
        public_id: str,
        *,
        idempotency_key: str,
    ) -> OfficialLinkResult:
        return self._write(
            principal,
            public_id,
            operation="ACTION_OFFICIAL_LINK",
            event_type=ActionEventType.OFFICIAL_LINK_OPENED,
            payload={},
            idempotency_key=idempotency_key,
            mutation=lambda saved, state, items: (saved, state, items),
            record_noop=True,
        )

    def _write(
        self,
        principal: Principal,
        public_id: str,
        *,
        operation: str,
        event_type: ActionEventType,
        payload: dict[str, object],
        idempotency_key: str,
        mutation: ActionMutation,
        record_noop: bool,
    ) -> OfficialLinkResult:
        self._assert_action_tracking_allowed(principal)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                detail, opportunity = self._governed_opportunity(session, public_id)
                event_payload = {
                    **payload,
                    "opportunity_id": str(opportunity.opportunity_id),
                    "opportunity_version": detail.current_version,
                }
                if event_type is ActionEventType.OFFICIAL_LINK_OPENED:
                    event_payload["official_url"] = str(detail.application_url)
                request_sha256 = _canonical_sha256(
                    {
                        "user_id": str(principal.user_id),
                        "operation": operation,
                        "public_id": public_id,
                        "payload": event_payload,
                    }
                )
                recorded = session.get(
                    PersonalIdempotencyRecordModel,
                    (principal.user_id, operation, key_sha256),
                )
                if recorded is not None:
                    if recorded.request_sha256 != request_sha256:
                        raise IdempotencyConflict("idempotency key conflict")
                    snapshot = self._owned_snapshot(
                        session,
                        principal.user_id,
                        recorded.resource_id,
                    )
                    if snapshot is None:
                        raise ActionUnavailable("personal action unavailable")
                    session.rollback()
                    return self._official_result(session, snapshot, detail.application_url)

                current = self._current_row(
                    session,
                    principal.user_id,
                    opportunity.opportunity_id,
                )
                current_values = self._values_from_row(current)
                desired_values = mutation(*current_values)
                if current is not None and desired_values == current_values and not record_noop:
                    self._record_idempotency(
                        session,
                        principal.user_id,
                        operation,
                        key_sha256,
                        request_sha256,
                        current,
                        created_at,
                    )
                    session.commit()
                    return self._official_result(session, current, detail.application_url)

                snapshot_id = self._id_factory()
                action_id = self._id_factory() if current is None else current.action_id
                version = 1 if current is None else current.version + 1
                event_id = self._id_factory()
                saved, state, material_items = desired_values
                input_sha256 = _canonical_sha256(
                    {
                        "previous_snapshot_id": (
                            None if current is None else str(current.action_snapshot_id)
                        ),
                        "user_id": str(principal.user_id),
                        "opportunity_id": str(opportunity.opportunity_id),
                        "opportunity_version": detail.current_version,
                        "saved": saved,
                        "state": state.value,
                        "material_items": [item.model_dump(mode="json") for item in material_items],
                        "event_type": event_type.value,
                        "event_payload": event_payload,
                    }
                )
                snapshot = PersonalActionSnapshotModel(
                    action_snapshot_id=snapshot_id,
                    action_id=action_id,
                    user_id=principal.user_id,
                    version=version,
                    opportunity_id=opportunity.opportunity_id,
                    opportunity_version=detail.current_version,
                    saved=saved,
                    state=state.value,
                    material_items=[item.model_dump(mode="json") for item in material_items],
                    last_event_id=event_id,
                    input_sha256=input_sha256,
                    created_at=created_at,
                )
                session.add(snapshot)
                session.flush()
                event = PersonalActionEventModel(
                    event_id=event_id,
                    action_id=action_id,
                    action_snapshot_id=snapshot_id,
                    user_id=principal.user_id,
                    event_type=event_type.value,
                    payload_sha256=_canonical_sha256(event_payload),
                    occurred_at=created_at,
                )
                session.add(event)
                session.flush()
                self._record_idempotency(
                    session,
                    principal.user_id,
                    operation,
                    key_sha256,
                    request_sha256,
                    snapshot,
                    created_at,
                )
                session.commit()
                return OfficialLinkResult(
                    official_url=detail.application_url,
                    action=self._snapshot_contract(snapshot),
                    event=self._event_contract(event),
                )
            except IntegrityError:
                session.rollback()
                recorded = session.get(
                    PersonalIdempotencyRecordModel,
                    (principal.user_id, operation, key_sha256),
                )
                if recorded is not None and recorded.request_sha256 == request_sha256:
                    snapshot = self._owned_snapshot(
                        session,
                        principal.user_id,
                        recorded.resource_id,
                    )
                    if snapshot is not None:
                        detail, _ = self._governed_opportunity(session, public_id)
                        return self._official_result(
                            session,
                            snapshot,
                            detail.application_url,
                        )
                raise
            except Exception:
                session.rollback()
                raise

    def _assert_action_tracking_allowed(self, principal: Principal) -> None:
        if not self._action_tracking_allowed(principal):
            raise ActionUnavailable("personal action unavailable")

    def _action_tracking_allowed(self, principal: Principal) -> bool:
        state = self._profile_service.get_current(principal)
        return state is not None and UserDataPurpose.ACTION_TRACKING in state.allowed_purposes

    @staticmethod
    def _governed_opportunity(
        session: Session,
        public_id: str,
    ) -> tuple[PublicOpportunityDetail, Opportunity]:
        detail = PublicCatalogService(session).get_opportunity(public_id)
        opportunity = session.scalar(select(Opportunity).where(Opportunity.public_id == public_id))
        if (
            detail is None
            or opportunity is None
            or opportunity.current_version != detail.current_version
        ):
            raise ActionUnavailable("personal action unavailable")
        return detail, opportunity

    @staticmethod
    def _current_row(
        session: Session,
        user_id: UUID,
        opportunity_id: UUID,
    ) -> PersonalActionSnapshotModel | None:
        return session.scalar(
            select(PersonalActionSnapshotModel)
            .where(
                PersonalActionSnapshotModel.user_id == user_id,
                PersonalActionSnapshotModel.opportunity_id == opportunity_id,
            )
            .order_by(PersonalActionSnapshotModel.version.desc())
            .limit(1)
        )

    @staticmethod
    def _owned_snapshot(
        session: Session,
        user_id: UUID,
        snapshot_id: UUID,
    ) -> PersonalActionSnapshotModel | None:
        return session.scalar(
            select(PersonalActionSnapshotModel).where(
                PersonalActionSnapshotModel.action_snapshot_id == snapshot_id,
                PersonalActionSnapshotModel.user_id == user_id,
            )
        )

    @staticmethod
    def _values_from_row(row: PersonalActionSnapshotModel | None) -> ActionValues:
        if row is None:
            return False, ActionState.NOT_STARTED, ()
        return (
            row.saved,
            ActionState(row.state),
            tuple(MaterialPlanItemSchemaV05.model_validate(item) for item in row.material_items),
        )

    @staticmethod
    def _record_idempotency(
        session: Session,
        user_id: UUID,
        operation: str,
        key_sha256: str,
        request_sha256: str,
        snapshot: PersonalActionSnapshotModel,
        created_at: datetime,
    ) -> None:
        session.add(
            PersonalIdempotencyRecordModel(
                user_id=user_id,
                operation=operation,
                key_sha256=key_sha256,
                request_sha256=request_sha256,
                resource_kind="ACTION",
                resource_id=snapshot.action_snapshot_id,
                response_version=snapshot.version,
                created_at=created_at,
            )
        )
        session.flush()

    @staticmethod
    def _snapshot_contract(
        row: PersonalActionSnapshotModel,
    ) -> PersonalActionSnapshotSchemaV05:
        return PersonalActionSnapshotSchemaV05.model_validate(
            {
                "action_snapshot_id": row.action_snapshot_id,
                "action_id": row.action_id,
                "version": row.version,
                "opportunity_id": row.opportunity_id,
                "opportunity_version": row.opportunity_version,
                "saved": row.saved,
                "state": row.state,
                "material_items": row.material_items,
                "last_event_id": row.last_event_id,
                "input_sha256": row.input_sha256,
                "created_at": row.created_at,
            }
        )

    @staticmethod
    def _event_contract(
        row: PersonalActionEventModel,
    ) -> PersonalActionEventSchemaV05:
        return PersonalActionEventSchemaV05.model_validate(
            {
                "event_id": row.event_id,
                "action_id": row.action_id,
                "action_snapshot_id": row.action_snapshot_id,
                "event_type": row.event_type,
                "payload_sha256": row.payload_sha256,
                "occurred_at": row.occurred_at,
            }
        )

    @staticmethod
    def _official_result(
        session: Session,
        snapshot: PersonalActionSnapshotModel,
        official_url: HttpUrl,
    ) -> OfficialLinkResult:
        event = session.get(PersonalActionEventModel, snapshot.last_event_id)
        if event is None or event.user_id != snapshot.user_id:
            raise ActionUnavailable("personal action unavailable")
        return OfficialLinkResult(
            official_url=official_url,
            action=ActionService._snapshot_contract(snapshot),
            event=ActionService._event_contract(event),
        )


__all__ = ["ActionService", "ActionUnavailable"]
