import type { CrossLevelReview } from "./cross-level";
export interface RelationIndex {
  task_id: string; target_plan_id: string;
  proposals: { proposal_id: string; producer_id: string; created_at: string }[];
}
export interface RelationDecision {
  decision_id: string; proposal_id: string; reviewer_id: string; sequence: number;
  previous_decision_id: string | null; created_at: string;
  decision: "APPROVE" | "REJECT" | "NEEDS_ADJUDICATION"; reason: string;
}
export interface RelationView {
  proposal_id: string; proposal_payload_sha256: string; payload_sha256: string;
  package: { proposal: { proposal_id: string; producer_id: string; relation: string; reason: string;
    source_review: CrossLevelReview; condition_ids: string[]; displaced_condition_ids: string[];
    evidence: { quote: string; source_url: string; locator: unknown; purpose: string }[];
  }; decisions: RelationDecision[] };
  review: { proposal_id: string; status: "UNREVIEWED" | "APPROVED" | "REJECTED" | "NEEDS_ADJUDICATION" | "STALE";
    latest: RelationDecision | null; executable: false; overall_qualification: "UNCERTAIN" };
}
export type RelationResult<T> = { ok: true; value: T } | { ok: false; error: string };
export const relationStatus = { UNREVIEWED: "待独立审核", APPROVED: "关系提案审核通过", REJECTED: "关系提案已拒绝", NEEDS_ADJUDICATION: "需要进一步裁决", STALE: "依据已变化，旧决定失效" };
export const relationKinds: Record<string, string> = { CUMULATIVE: "条件累积", EXCEPTION: "例外关系", CONFLICT: "条件冲突", UNRESOLVED: "关系尚未确定" };
export function relationPath(task: string, plan: string, proposal?: string) {
  const base = `/review/investigations/${encodeURIComponent(task)}/unit-plans/${encodeURIComponent(plan)}/relations`;
  return proposal ? `${base}?proposal=${encodeURIComponent(proposal)}` : base;
}
