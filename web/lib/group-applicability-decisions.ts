import type { ApplicabilityDecision, ApplicabilityRequest } from "./rule-applicability";
import type { GroupApplicabilityContext, GroupApplicabilityView } from "./group-applicability";

export interface GroupApplicabilityRequest extends ApplicabilityRequest {
  contract_version: "group-applicability-decision/1.0.0";
}
export interface GroupApplicabilityDecision extends Omit<ApplicabilityDecision, "context" | "request"> {
  request: GroupApplicabilityRequest;
  context: GroupApplicabilityContext;
}
export interface GroupApplicabilityHistory extends Omit<GroupApplicabilityView, "scope" | "outcome" | "evidence_options" | "next_cursor"> {
  scope: "GROUP_APPLICABILITY_REVIEW_ONLY";
  history: GroupApplicabilityDecision[];
  latest: GroupApplicabilityDecision | null;
}
export interface GroupApplicabilityReviewView extends GroupApplicabilityView {
  decisions: GroupApplicabilityHistory;
}
