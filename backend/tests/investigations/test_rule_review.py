from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid7

from sqlalchemy.orm import Session

from deepaha.investigations.contracts import digest
from deepaha.investigations.models import InvestigationRuleDecision, InvestigationRulePreparation
from deepaha.investigations.rules import describe_rule_preparation


def test_final_decision_is_not_hidden_by_later_returned_pending_record() -> None:
    candidate_id = uuid7()
    prep = InvestigationRulePreparation(
        rule_preparation_id=uuid7(),
        fact_preparation_id=uuid7(),
        entity_id="position",
        fact_set_id=uuid7(),
        compiler_version="synthetic",
        result={},
        result_hash=digest({}),
    )
    session = Mock(spec=Session)
    session.scalars.return_value = [
        InvestigationRuleDecision(
            decision_id=uuid7(),
            rule_candidate_id=candidate_id,
            reviewer_id=uuid7(),
            created_at=datetime.now(UTC),
            request={"decision": decision, "reason": "Synthetic", "evidence": []},
        )
        for decision in ["APPROVE", "NEEDS_ADJUDICATION"]
    ]
    view = describe_rule_preparation(session, prep)
    assert view["decisions"][str(candidate_id)]["decision"] == "APPROVE"
    assert len(view["decision_history"]) == 2
