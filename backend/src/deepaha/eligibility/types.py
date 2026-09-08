from typing import Protocol
from uuid import UUID

from deepaha.rules.types import CompiledRule


class RuleEvaluationGraph(Protocol):
    @property
    def rules(self) -> tuple[CompiledRule, ...]: ...

    @property
    def root_rule_ids(self) -> tuple[UUID, ...]: ...
