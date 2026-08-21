from deepaha.opportunities.models import Opportunity
from deepaha.opportunities.resolver import resolve_document
from deepaha.opportunities.types import (
    UNSET,
    OpportunityPatch,
    ResolutionDecision,
    ResolutionDocument,
    ResolutionIndex,
    ResolutionTarget,
)

__all__ = [
    "UNSET",
    "Opportunity",
    "OpportunityPatch",
    "ResolutionDecision",
    "ResolutionDocument",
    "ResolutionIndex",
    "ResolutionTarget",
    "resolve_document",
]
