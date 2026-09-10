import type { GroupFactRecord, GroupFactResult } from "./group-facts";
export interface GroupRuleRow {
  source_index: number; candidate_id: string | null; verified_fact_id: string | null;
  fact_state: "KNOWN" | "UNKNOWN" | null; normalized_value: unknown;
  proposed_rule_payload: { code: string; field: string; operator: string; value_type: string; value: unknown; required: boolean; reason_template: string } | null;
  evidence_ref_ids: string[];
  reason_code: "GROUP_FIELD_UNPROCESSED" | "FACT_REJECTED" | "FACT_SET_NOT_SAVED" | "FACT_UNKNOWN" | "FIELD_NOT_EXECUTABLE" | "INDEPENDENT_RULE_REVIEW_REQUIRED";
}
export interface GroupRulePreview {
  result: { contract_version: "group-rule-preview/1.0.0"; derivation_version: string; scope: "READ_ONLY_GROUP_RULE_PREVIEW";
    target: GroupFactRecord["result"]["group_source"]["group_identity"]; fact_review: GroupFactRecord; rows: GroupRuleRow[] };
  result_hash: string;
}
export type GroupRuleResult = { ok: true; value: GroupRulePreview } | Exclude<GroupFactResult, { ok: true }>;
export function groupRulePath(taskId: string, prepId: string) { return `/review/investigations/${encodeURIComponent(taskId)}/group-facts/${encodeURIComponent(prepId)}/rules`; }
export const groupRuleReasons: Record<GroupRuleRow["reason_code"], string> = {
  GROUP_FIELD_UNPROCESSED: "待处理：字段或证据尚不能用于规则",
  FACT_REJECTED: "候选已拒绝；不表示条件不适用",
  FACT_SET_NOT_SAVED: "尚未保存正式事实集",
  FACT_UNKNOWN: "事实未知，不能形成资格规则",
  FIELD_NOT_EXECUTABLE: "已知事实不属于可执行资格条件",
  INDEPENDENT_RULE_REVIEW_REQUIRED: "可预览规则，仍需独立规则审核",
};
