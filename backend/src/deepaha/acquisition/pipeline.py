from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.documents.service import DocumentService, ParseDocumentCommand, ParseDocumentResult


class AcquisitionDocumentBlocked(RuntimeError):
    def __init__(self) -> None:
        self.code = "ACQUISITION_DOCUMENT_BLOCKED"
        super().__init__(self.code)


def advance_valid_artifact(
    *,
    session_factory: sessionmaker[Session],
    document_service: DocumentService,
    acquisition_evaluation_id: UUID,
) -> ParseDocumentResult:
    with session_factory() as session:
        evaluation = session.get(AcquisitionEvaluation, acquisition_evaluation_id)
        if evaluation is None:
            raise LookupError(f"AcquisitionEvaluation not found: {acquisition_evaluation_id}")
        if evaluation.validation_status != "VALID":
            raise AcquisitionDocumentBlocked
        artifact_id = evaluation.artifact_id

    return document_service.parse(ParseDocumentCommand(artifact_id=artifact_id))


__all__ = ["AcquisitionDocumentBlocked", "advance_valid_artifact"]
