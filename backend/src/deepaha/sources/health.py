from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import ParseAttempt
from deepaha.sources.models import CaptureObservation, SourceEndpoint


@dataclass(frozen=True, slots=True)
class SourceHealthSummary:
    endpoint_id: UUID
    source_id: UUID
    as_of: datetime
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    attempts_24h: int
    successes_24h: int
    not_modified_24h: int
    failures_24h: int
    latest_artifact_id: UUID | None
    latest_content_sha256: str | None
    latest_object_key: str | None
    parse_successes: int
    parse_needs_review: int
    parse_failures: int


def get_source_health(
    session: Session,
    endpoint_id: UUID,
    as_of: datetime,
) -> SourceHealthSummary:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include timezone information")
    normalized_as_of = as_of.astimezone(UTC)
    endpoint = session.get(SourceEndpoint, endpoint_id)
    if endpoint is None:
        raise LookupError(f"SourceEndpoint not found: {endpoint_id}")

    observations = list(
        session.scalars(
            select(CaptureObservation)
            .where(
                CaptureObservation.endpoint_id == endpoint_id,
                CaptureObservation.completed_at <= normalized_as_of,
            )
            .order_by(
                CaptureObservation.completed_at.desc(),
                CaptureObservation.observation_id.desc(),
            )
        )
    )
    cutoff = normalized_as_of - timedelta(hours=24)
    recent = [row for row in observations if row.completed_at >= cutoff]
    last_success = next(
        (row for row in observations if row.outcome in {"SUCCEEDED", "NOT_MODIFIED"}),
        None,
    )
    latest_artifact_observation = next(
        (row for row in observations if row.artifact_id is not None),
        None,
    )
    latest_artifact = (
        session.get(RawArtifact, latest_artifact_observation.artifact_id)
        if latest_artifact_observation is not None
        and latest_artifact_observation.artifact_id is not None
        else None
    )

    artifact_ids = {row.artifact_id for row in observations if row.artifact_id is not None}
    parse_outcomes: list[str] = []
    if artifact_ids:
        parse_outcomes = list(
            session.scalars(
                select(ParseAttempt.outcome).where(
                    ParseAttempt.artifact_id.in_(artifact_ids),
                    ParseAttempt.completed_at <= normalized_as_of,
                )
            )
        )

    return SourceHealthSummary(
        endpoint_id=endpoint.endpoint_id,
        source_id=endpoint.source_id,
        as_of=normalized_as_of,
        last_attempt_at=observations[0].completed_at if observations else None,
        last_success_at=last_success.completed_at if last_success is not None else None,
        consecutive_failures=_consecutive_failures(observations),
        attempts_24h=len(recent),
        successes_24h=sum(row.outcome == "SUCCEEDED" for row in recent),
        not_modified_24h=sum(row.outcome == "NOT_MODIFIED" for row in recent),
        failures_24h=sum(row.outcome == "FAILED" for row in recent),
        latest_artifact_id=latest_artifact.artifact_id if latest_artifact is not None else None,
        latest_content_sha256=(
            latest_artifact.content_sha256 if latest_artifact is not None else None
        ),
        latest_object_key=latest_artifact.object_key if latest_artifact is not None else None,
        parse_successes=parse_outcomes.count("SUCCEEDED"),
        parse_needs_review=parse_outcomes.count("NEEDS_REVIEW"),
        parse_failures=parse_outcomes.count("FAILED"),
    )


def _consecutive_failures(observations: list[CaptureObservation]) -> int:
    count = 0
    for observation in observations:
        if observation.outcome != "FAILED":
            break
        count += 1
    return count


__all__ = ["SourceHealthSummary", "get_source_health"]
