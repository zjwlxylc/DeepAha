from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import EgressDecisionSchemaV08, ModelTaskSpecSchemaV08
from deepaha.p9b.models import EgressDecision, ModelTaskSpec


class EgressRepository:
    """Persist typed Gateway authority inputs; database triggers remain authoritative."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_task_spec(self, task: ModelTaskSpecSchemaV08) -> ModelTaskSpec:
        record = ModelTaskSpec(**task.model_dump(mode="python"))
        self._session.add(record)
        self._session.flush()
        return record

    def persist_decision(self, decision: EgressDecisionSchemaV08) -> EgressDecision:
        record = EgressDecision(**decision.model_dump(mode="python"))
        self._session.add(record)
        self._session.flush()
        return record
