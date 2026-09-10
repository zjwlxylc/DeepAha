import type { GroupRulePreview, GroupRuleResult, GroupRuleRow } from "./group-rules";
export const groupRuleReviewVersion = "group-rule-review/1.0.0+deriver-1.0.1";
export const evidenceAuthorities = {
  LATEST_OFFICIAL_CORRECTION: "最新官方更正", FORMAL_OFFICIAL_ATTACHMENT: "正式官方附件",
  ORIGINAL_OFFICIAL_NOTICE: "原始正式公告", OFFICIAL_FAQ_GUIDANCE: "官方问答/指南",
  HUMAN_APPROVED_MAPPING: "人工批准映射", LLM_SEMANTIC_INFERENCE: "模型语义推断",
} as const;
export interface GroupRuleAssessment {
  evidence_ref_id: string; authority: keyof typeof evidenceAuthorities | null;
  relation: "SUPPORTS" | "CONTRADICTS" | null; effective_at: string | null;
  applicability: "APPLIES_TO_EXACT_TARGET" | "UNRESOLVED"; reason: string;
}
export interface GroupRuleDecision {
  decision_id: string; rule_candidate_id: string; decision: "APPROVE" | "REJECT" | "NEEDS_ADJUDICATION";
  reason: string; evidence: GroupRuleAssessment[]; reviewer_id: string; created_at: string;
}
export interface GroupRuleReviewRecord {
  preparation_id: string; fact_preparation_id: string; fact_set_id: string;
  result: { contract_version: typeof groupRuleReviewVersion; scope: "GROUP_RULE_REVIEW_ONLY"; preview: GroupRulePreview; rows: (GroupRuleRow & { rule_candidate_id: string | null })[] };
  result_hash: string; reviewer_id: string; created_at: string;
  decisions: Record<string, GroupRuleDecision>; history: GroupRuleDecision[];
}
export type GroupRuleReviewResult = { ok: true; value: GroupRuleReviewRecord } | Exclude<GroupRuleResult, { ok: true }>;
export type GroupRuleReviewCommand = { kind: "prepare"; fact_preparation_id: string; expected_preview_hash: string }
  | { kind: "decision"; preparation_id: string; expected_preparation_hash: string; rule_candidate_id: string; decision: GroupRuleDecision["decision"]; reason: string; evidence: GroupRuleAssessment[] };
export function groupRuleReviewPath(task: string, preparation: string) { return `/review/investigations/${encodeURIComponent(task)}/group-rules/${encodeURIComponent(preparation)}`; }
