from dataclasses import dataclass

from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectStore
from deepaha.artifacts.service import (
    ImportRawArtifactCommand,
    _insert_or_load_raw_artifact,
    _prepare_raw_artifact,
)


@dataclass(frozen=True, slots=True)
class ObservedRawArtifactResult:
    artifact: RawArtifact
    created: bool


def import_observed_raw_artifact(
    *,
    session: Session,
    object_store: ObjectStore,
    command: ImportRawArtifactCommand,
) -> ObservedRawArtifactResult:
    prepared = _prepare_raw_artifact(
        object_store=object_store,
        command=command,
        require_matching_media_type=False,
    )
    result = _insert_or_load_raw_artifact(session, prepared)
    return ObservedRawArtifactResult(artifact=result.artifact, created=result.created)


__all__ = ["ObservedRawArtifactResult", "import_observed_raw_artifact"]
