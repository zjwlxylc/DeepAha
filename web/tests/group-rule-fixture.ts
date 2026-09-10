import type { GroupFactData } from "../lib/group-facts";
import type { GroupRulePreview } from "../lib/group-rules";
import { createHash } from "node:crypto";
export function groupRuleFixture(data: GroupFactData): GroupRulePreview {
  const record = data.record!;
  for (const [index, row] of record.result.rows.entries()) {
    if (!row.candidate_id) continue;
    const decision = { candidate_id: row.candidate_id, decision_id: `019d0000-0000-7000-8000-00000000600${index}`, decision: row.abstained ? "UNKNOWN" as const : "APPROVE" as const, reason: "合成字段审核", reviewer_id: record.reviewer_id, created_at: record.created_at };
    record.decisions[row.candidate_id] = decision;
  }
  record.history = Object.values(record.decisions);
  record.fact_set = { fact_set_id: "019d0000-0000-7000-8000-000000006099", status: "ACTIVE", version: 1, reason: "合成事实集" };
  const result: GroupRulePreview["result"] = { contract_version: "group-rule-preview/1.0.0", derivation_version: "1.0.1", scope: "READ_ONLY_GROUP_RULE_PREVIEW", target: record.result.group_source.group_identity, fact_review: record,
    rows: record.result.rows.map((row, index) => ({ source_index: row.source_index, candidate_id: row.candidate_id,
      verified_fact_id: row.candidate_id ? `019d0000-0000-7000-8000-00000000700${index}` : null,
      fact_state: !row.candidate_id ? null : row.abstained ? "UNKNOWN" : "KNOWN", normalized_value: row.candidate_id ? row.normalized_value_candidate : null,
      proposed_rule_payload: row.candidate_id && !row.abstained ? { code: `group-preview-019d0000-0000-7000-8000-00000000700${index}`, field: "education_level", operator: "GTE", value_type: "STRING", value: "MASTER", required: true, reason_template: "学历必须满足官方最低要求" } : null,
      evidence_ref_ids: row.candidate_id ? [...new Set(row.evidence.map(e => e.binding!.evidence_ref_id))].sort() : [],
      reason_code: !row.candidate_id ? "GROUP_FIELD_UNPROCESSED" : row.abstained ? "FACT_UNKNOWN" : "INDEPENDENT_RULE_REVIEW_REQUIRED" })) };
  const json = JSON.stringify(result, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item);
  return { result, result_hash: createHash("sha256").update(json).digest("hex") };
}
