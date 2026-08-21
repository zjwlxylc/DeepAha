from deepaha.opportunities.models import Opportunity
from deepaha.opportunities.resolver import resolve_document
from deepaha.opportunities.service import (
    OpportunityResolutionService,
    ResolutionResult,
    load_resolution_index,
)
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
    "OpportunityResolutionService",
    "ResolutionDecision",
    "ResolutionDocument",
    "ResolutionIndex",
    "ResolutionTarget",
    "ResolutionResult",
    "load_resolution_index",
    "resolve_document",
]
