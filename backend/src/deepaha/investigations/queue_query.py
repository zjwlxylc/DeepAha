"""One-query summaries. Cursors are navigation data, never authorization."""

import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select, tuple_

from deepaha.investigations.contracts import digest
from deepaha.investigations.models import STATES, InvestigationMaterial, InvestigationTask
from deepaha.investigations.store import InvestigationStore


class QueueQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    source: UUID | None = None
    q: str = Field(default="", max_length=200)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in STATES:
            raise ValueError("invalid status")
        return value


def read_queue(store: InvestigationStore, query: QueueQuery) -> dict[str, Any]:
    filters = {"status": query.status, "source": str(query.source), "q": query.q.strip()}
    boundary = None
    upper = None
    if query.cursor:
        try:
            raw = base64.b64decode(query.cursor, altchars=b"-_", validate=True)
            payload = json.loads(raw)
            checksum = payload.pop("checksum")
            if checksum != digest(payload) or payload["filters"] != filters or payload["v"] != 1:
                raise ValueError("cursor mismatch")
            boundary = (datetime.fromisoformat(payload["after"][0]), UUID(payload["after"][1]))
            upper = (datetime.fromisoformat(payload["upper"][0]), UUID(payload["upper"][1]))
            if boundary[0].tzinfo is None or upper[0].tzinfo is None or boundary > upper:
                raise ValueError("invalid boundary")
        except ValueError, KeyError, TypeError, AttributeError, IndexError:
            raise ValueError("INVALID_QUEUE_CURSOR") from None
    task = InvestigationTask
    title = func.coalesce(
        task.delivery["opportunities"]["opportunity_name"].astext, task.request["brief"].astext
    )
    materials = (
        select(func.count())
        .select_from(InvestigationMaterial)
        .where(InvestigationMaterial.task_id == task.task_id)
        .scalar_subquery()
    )
    statement = select(
        task.task_id,
        task.source_id,
        task.status,
        task.created_at,
        task.updated_at,
        task.error_code,
        task.dispatch_requested_at,
        task.dispatch_context["finished_at"].astext.label("dispatch_finished_at"),
        task.runtime_id,
        task.remote_session_id,
        func.left(title, 300).label("title"),
        task.request["notice_url"].astext.label("notice_url"),
        task.request["calibration"].as_boolean().label("calibration"),
        materials.label("material_count"),
    )
    if query.status:
        statement = statement.where(task.status == query.status)
    if query.source:
        statement = statement.where(task.source_id == query.source)
    if filters["q"]:
        term = str(filters["q"])
        statement = statement.where(
            or_(
                title.icontains(term, autoescape=True),
                task.request["notice_url"].astext.icontains(term, autoescape=True),
            )
        )
    if boundary and upper:
        statement = statement.where(
            tuple_(task.created_at, task.task_id) < boundary,
            tuple_(task.created_at, task.task_id) <= upper,
        )
    statement = statement.order_by(task.created_at.desc(), task.task_id.desc()).limit(
        query.limit + 1
    )
    with store.factory() as session:
        rows = list(session.execute(statement).mappings())
    items = []
    for row in rows[: query.limit]:
        item = dict(row)
        for key in ("task_id", "source_id"):
            item[key] = str(item[key])
        for key in ("created_at", "updated_at", "dispatch_requested_at"):
            item[key] = item[key].isoformat() if item[key] else None
        finished_at = item.pop("dispatch_finished_at")
        item["dispatch_pending"] = bool(row["dispatch_requested_at"] and not finished_at)
        item["next_step"] = (
            "确认单位和岗位"
            if row["status"] == "APPROVED"
            else "核对材料"
            if row["status"] == "PENDING_REVIEW"
            else "查看任务状态"
        )
        items.append(item)
    cursor = None
    if len(rows) > query.limit:
        first, last = rows[0], rows[query.limit - 1]
        upper = upper or (first["created_at"], first["task_id"])
        payload = {
            "v": 1,
            "filters": filters,
            "upper": [upper[0].isoformat(), str(upper[1])],
            "after": [last["created_at"].isoformat(), str(last["task_id"])],
        }
        payload["checksum"] = digest(payload)
        cursor = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    return {"tasks": items, "next_cursor": cursor}
