import "server-only";

import { cookies } from "next/headers";

import type { FeedbackClaimKind, FeedbackReviewStatus } from "./feedback";

export interface ReviewQueueItem {
  review_case_id: string;
  feedback_event_id: string;
  version: number;
  status: FeedbackReviewStatus;
  priority: number;
  due_at: string;
  overdue: boolean;
  claim_kind: FeedbackClaimKind;
  opportunity_public_id: string;
  opportunity_title: string;
  opportunity_version: number;
  created_at: string;
}

export interface ReviewCaseHistoryItem {
  version: number;
  status: FeedbackReviewStatus;
  priority: number;
  due_at: string;
  transition_reason: string;
  created_at: string;
}

export interface ReviewEvidenceItem {
  evidence_ref_id: string;
  document_id: string;
  locator_kind: string;
  locator_value: string | null;
  relation: "SUPPORTS" | "CONTRADICTS";
  actor_kind: "USER" | "REVIEWER";
  note: string | null;
  created_at: string;
}

export interface ConfidenceAssessmentResult {
  confidence_assessment_id: string;
  review_case_id: string;
  review_case_version: number;
  evidence_complete: boolean;
  confidence_band: "LOW" | "MEDIUM" | "HIGH";
  risk_level: "NORMAL" | "HIGH_IMPACT";
  conflict: boolean;
  evidence_ref_ids: string[];
  rationale: string;
  created_at: string;
}

export interface FeedbackAdjudicationResult {
  feedback_adjudication_id: string;
  review_case_id: string;
  review_case_version: number;
  confidence_assessment_id: string;
  decision: "NEEDS_EVIDENCE" | "CONFLICT" | "CONFIRMED" | "REJECTED";
  evidence_ref_ids: string[];
  reason: string;
  created_at: string;
  resulting_case_version: number;
}

export interface ReviewCaseDetail {
  case: ReviewQueueItem;
  user_statement: string | null;
  structured_reason_code: string;
  match_snapshot_id: string;
  history: ReviewCaseHistoryItem[];
  evidence: ReviewEvidenceItem[];
  latest_assessment: ConfidenceAssessmentResult | null;
  latest_adjudication: FeedbackAdjudicationResult | null;
  approved_label_id: string | null;
}

export interface ReviewQueuePage {
  items: ReviewQueueItem[];
}

export class ReviewApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ReviewApiError";
  }
}

export async function reviewFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = (await cookies()).get("deepaha_phase7_reviewer_session")?.value;
  if (!token) {
    throw new ReviewApiError(401, "Reviewer session required");
  }
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    throw new ReviewApiError(response.status, "Review request failed");
  }
  return (await response.json()) as T;
}

export function getReviewQueue(): Promise<ReviewQueuePage> {
  return reviewFetch<ReviewQueuePage>("/api/v1/review/feedback");
}

export function getReviewCase(reviewCaseId: string): Promise<ReviewCaseDetail> {
  return reviewFetch<ReviewCaseDetail>(
    `/api/v1/review/feedback/${encodeURIComponent(reviewCaseId)}`,
  );
}
