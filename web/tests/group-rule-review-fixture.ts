import type { GroupRulePreview } from "../lib/group-rules";
import type { GroupRuleReviewRecord } from "../lib/group-rule-review";
import { createHash } from "node:crypto";
function fixtureHash(value: unknown) { return createHash("sha256").update(JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item)).digest("hex"); }
export function groupRuleReviewFixture(input: GroupRulePreview): GroupRuleReviewRecord {
  const preview = structuredClone(input);
  const result: GroupRuleReviewRecord["result"] = { contract_version: "group-rule-review/1.0.0+deriver-1.0.1", scope: "GROUP_RULE_REVIEW_ONLY", preview,
    rows: preview.result.rows.map((row, i) => ({ ...row, rule_candidate_id: row.proposed_rule_payload ? `019d0000-0000-7000-8000-00000000800${i}` : null })) };
  return { preparation_id: "019d0000-0000-7000-8000-000000008099", fact_preparation_id: preview.result.fact_review.preparation_id,
    fact_set_id: preview.result.fact_review.fact_set!.fact_set_id, result, result_hash: fixtureHash(result),
    reviewer_id: preview.result.fact_review.reviewer_id, created_at: preview.result.fact_review.created_at, decisions: {}, history: [] };
}
