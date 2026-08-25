from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    EgressBlockClassificationSchemaV08,
    EgressDecisionSchemaV08,
    ModelTaskSpecSchemaV08,
    ProviderEgressPolicySnapshotSchemaV08,
    SourceEgressPolicySnapshotSchemaV08,
)
from deepaha.p9b.models import (
    EgressBlockClassification,
    EgressDecision,
    ModelTaskSpec,
    ProviderEgressPolicySnapshot,
    SourceEgressPolicySnapshot,
)


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

    def persist_block_classification(
        self,
        classification: EgressBlockClassificationSchemaV08,
    ) -> EgressBlockClassification:
        record = EgressBlockClassification(**classification.model_dump(mode="python"))
        self._session.add(record)
        self._session.flush()
        return record

    def persist_source_policy(
        self,
        policy: SourceEgressPolicySnapshotSchemaV08,
    ) -> SourceEgressPolicySnapshot:
        record = SourceEgressPolicySnapshot(**policy.model_dump(mode="python"))
        self._session.add(record)
        self._session.flush()
        return record

    def persist_provider_policy(
        self,
        policy: ProviderEgressPolicySnapshotSchemaV08,
    ) -> ProviderEgressPolicySnapshot:
        record = ProviderEgressPolicySnapshot(**policy.model_dump(mode="python"))
        self._session.add(record)
        self._session.flush()
        return record
