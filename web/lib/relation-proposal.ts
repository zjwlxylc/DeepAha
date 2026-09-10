import type { CrossLevelReview } from "./cross-level";
export interface ProposalContext {
  task_id: string; target_plan_id: string; review_hash: string; review: CrossLevelReview;
  evidence_options: { member_id: string; block_id: string; material_id: string; source_url: string; text: string; locator: unknown }[];
  next_cursor: string | null;
}
export interface ProposalRequest {
  target_plan_id: string; expected_review_hash: string; condition_ids: string[];
  relation: string; displaced_condition_ids: string[]; reason: string;
  evidence: { member_id: string; block_id: string; quote: string; purpose: string; condition_ids: string[] }[];
}
