"use server";
import { createHash } from "node:crypto";
import { loadGroupFactRecordAction } from "./group-fact-actions";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import type { GroupRulePreview, GroupRuleResult } from "../../../lib/group-rules";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function stable(value: unknown) { return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item); }
function mismatch(): never { throw new LocalHumanTestApiError(409); }
export async function loadGroupRulePreviewAction(taskId: string, prepId: string): Promise<GroupRuleResult> {
  if (!uuid.test(taskId) || !uuid.test(prepId)) return { ok: false, kind: "invalid", error: "请从已保存的组字段审核记录进入规则预览。" };
  try {
    const preview = await humanTestFetch<GroupRulePreview>(`/investigations/${taskId}/group-facts/${prepId}/rules/preview`);
    const current = await loadGroupFactRecordAction(taskId, prepId);
    if (!current.ok) return current;
    const data = preview.result, record = current.value.record!;
    if (data.contract_version !== "group-rule-preview/1.0.0" || data.derivation_version !== "1.0.1" || data.scope !== "READ_ONLY_GROUP_RULE_PREVIEW"
      || preview.result_hash !== createHash("sha256").update(stable(data)).digest("hex")
      || stable(data.fact_review) !== stable(record) || stable(data.target) !== stable(record.result.group_source.group_identity)
      || (record.fact_set && record.fact_set.status !== "ACTIVE") || data.rows.length !== record.result.rows.length) mismatch();
    const factIds = new Set<string>();
    data.rows.forEach((row, index) => {
      const source = record.result.rows[index], decision = source.candidate_id ? record.decisions[source.candidate_id]?.decision : null;
      if (row.source_index !== source.source_index || row.candidate_id !== source.candidate_id) mismatch();
      const hasFact = !!record.fact_set && !!source.candidate_id && ["APPROVE", "UNKNOWN"].includes(decision ?? "");
      if (!hasFact) {
        const reason = !source.candidate_id ? "GROUP_FIELD_UNPROCESSED" : decision === "REJECT" ? "FACT_REJECTED" : "FACT_SET_NOT_SAVED";
        if (row.verified_fact_id !== null || row.fact_state !== null || row.normalized_value !== null || row.proposed_rule_payload !== null || row.evidence_ref_ids.length || row.reason_code !== reason) mismatch();
      } else {
        if (!row.verified_fact_id || !uuid.test(row.verified_fact_id) || factIds.has(row.verified_fact_id)) mismatch();
        factIds.add(row.verified_fact_id);
        const refs = [...new Set(source.evidence.map(e => e.binding!.evidence_ref_id))].sort();
        if (stable([...row.evidence_ref_ids].sort()) !== stable(refs)) mismatch();
        if (decision === "UNKNOWN") {
          if (row.fact_state !== "UNKNOWN" || row.normalized_value !== null || row.proposed_rule_payload !== null || row.reason_code !== "FACT_UNKNOWN") mismatch();
        } else {
          if (source.abstained || row.fact_state !== "KNOWN" || stable(row.normalized_value) !== stable(source.normalized_value_candidate)) mismatch();
          const payload = row.proposed_rule_payload;
          if (!payload) { if (row.reason_code !== "FIELD_NOT_EXECUTABLE") mismatch(); }
          else if (row.reason_code !== "INDEPENDENT_RULE_REVIEW_REQUIRED" || payload.code !== `group-preview-${row.verified_fact_id}`
            || payload.required !== true || !payload.reason_template?.trim() || payload.value == null
            || !["education_level", "major_code", "certificates", "hukou_region", "student_status", "birth_date"].includes(payload.field)
            || !["GTE", "IN", "CONTAINS_ALL", "BETWEEN"].includes(payload.operator)
            || !["STRING", "STRING_SET", "DATE"].includes(payload.value_type)) mismatch();
        }
      }
    });
    return { ok: true, value: preview };
  } catch (error) {
    if (error instanceof LocalHumanTestApiError) {
      if ([401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话无权读取组规则预览，旧内容已隐藏。" };
      if ([404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "组身份、事实或证据已变化，旧预览已隐藏。请重新核对组字段记录。" };
    }
    return { ok: false, kind: "unavailable", error: "暂未取得当前规则预览，旧内容已隐藏。可重新读取。" };
  }
}
