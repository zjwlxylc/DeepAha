import "server-only";

import { personalFetch } from "./personal-opportunities";

export type FeedbackClaimKind =
  | "ELIGIBILITY_CORRECTION"
  | "OPPORTUNITY_FACT_CORRECTION"
  | "EXPLANATION_UNCLEAR"
  | "RANKING_IRRELEVANT";

export type FeedbackReviewStatus =
  | "RECEIVED"
  | "NEEDS_EVIDENCE"
  | "CONFLICT"
  | "CONFIRMED"
  | "REJECTED";

export interface FeedbackStatusSummary {
  feedback_event_id: string;
  opportunity_public_id: string;
  opportunity_version: number;
  event_type: "STRUCTURED_CORRECTION" | "EXPLICIT_EVALUATION";
  claim_kind: FeedbackClaimKind;
  status: FeedbackReviewStatus;
  created_at: string;
  status_updated_at: string;
}

export interface FeedbackEvidenceSummary {
  feedback_evidence_link_id: string;
  evidence_ref_id: string;
  relation: "SUPPORTS" | "CONTRADICTS";
  note: string | null;
  created_at: string;
}

export interface FeedbackStatusDetail {
  feedback: FeedbackStatusSummary;
  evidence: FeedbackEvidenceSummary[];
}

export interface FeedbackStatusPage {
  items: FeedbackStatusSummary[];
}

export function listFeedback(): Promise<FeedbackStatusPage> {
  return personalFetch<FeedbackStatusPage>("/api/v1/me/feedback");
}

export function getFeedback(feedbackEventId: string): Promise<FeedbackStatusDetail> {
  return personalFetch<FeedbackStatusDetail>(
    `/api/v1/me/feedback/${encodeURIComponent(feedbackEventId)}`,
  );
}
