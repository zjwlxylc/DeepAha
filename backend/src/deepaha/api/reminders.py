from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session, sessionmaker

from deepaha.api.personal import (
    PRIVATE_CACHE_CONTROL,
    PersonalApiProblem,
    require_idempotency_key,
    require_principal,
)
from deepaha.contracts.phase8 import ReminderPreferenceSnapshotSchemaV07
from deepaha.db.session import get_write_session
from deepaha.notifications.preferences import (
    ReminderPreferenceAccessError,
    ReminderPreferenceIdempotencyConflict,
    ReminderPreferenceService,
)
from deepaha.notifications.schemas import ReminderPreferenceWrite
from deepaha.personal.auth import Principal

router = APIRouter(prefix="/api/v1/me", tags=["reminders"])


def get_reminder_preference_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> ReminderPreferenceService:
    return ReminderPreferenceService(
        session_factory=sessionmaker(
            bind=session.get_bind(),
            expire_on_commit=False,
        ),
        now_factory=lambda: datetime.now(UTC),
    )


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL


def _not_found() -> PersonalApiProblem:
    return PersonalApiProblem(
        status=404,
        slug="personal-resource-not-found",
        title="Personal resource not found",
        detail="The personal resource was not found.",
    )


def _conflict() -> PersonalApiProblem:
    return PersonalApiProblem(
        status=409,
        slug="idempotency-conflict",
        title="Idempotency conflict",
        detail="The idempotency key was already used for a different request.",
    )


@router.get("/reminder-preferences/deadline-change")
def get_deadline_change_preference(
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[
        ReminderPreferenceService,
        Depends(get_reminder_preference_service),
    ],
) -> ReminderPreferenceSnapshotSchemaV07 | None:
    result = service.get_current(principal)
    _private(response)
    return result


@router.put("/reminder-preferences/deadline-change")
def put_deadline_change_preference(
    command: ReminderPreferenceWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[
        ReminderPreferenceService,
        Depends(get_reminder_preference_service),
    ],
) -> ReminderPreferenceSnapshotSchemaV07:
    try:
        result = service.set_enabled(
            principal,
            command.enabled,
            idempotency_key=idempotency_key,
        )
    except ReminderPreferenceIdempotencyConflict as error:
        raise _conflict() from error
    except ReminderPreferenceAccessError as error:
        raise _not_found() from error
    _private(response)
    return result


__all__ = ["get_reminder_preference_service", "router"]
