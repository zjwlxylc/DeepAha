"use server";
import { createHash } from "node:crypto";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import type { GroupApplicabilityContext, GroupApplicabilityIdentity, GroupApplicabilityResult, GroupApplicabilityView } from "../../../lib/group-applicability";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function stable(value: unknown): string { return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item); }
function hash(value: unknown) { return createHash("sha256").update(stable(value)).digest("hex"); }
function fail(error: unknown): Exclude<GroupApplicabilityResult<never>, { ok: true }> {
  if (error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话无权查看，旧内容已隐藏。" };
  if (error instanceof LocalHumanTestApiError && [404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "来源、岗位或证据已变化，旧内容已隐藏。请重新读取。" };
  return { ok: false, kind: "unavailable", error: "未取得可靠的当前上下文，旧内容已隐藏。请稍后重试。" };
}
function checkContext(c: GroupApplicabilityContext, task: string, plan: string) {
  return c.contract_version === "group-rule-applicability-context/1.0.0" && c.task_id === task && c.target_plan_id === plan
    && uuid.test(c.source_rule_preparation_id) && uuid.test(c.source_rule_candidate_id)
    && c.source_group.unit_kind === "GROUP" && c.member.state === "BOUND" && c.member.entity_id === c.target_entity_id
    && c.member.position_binding?.entity_id === c.target_entity_id
    && c.member.position_binding.opportunity_unit_id === c.target.unit_id
    && c.member.position_binding.opportunity_unit_version_id === c.target.unit_version_id;
}
export async function loadGroupApplicabilityEntries(task: string, plan: string): Promise<GroupApplicabilityResult<GroupApplicabilityContext[]>> {
  if (![task, plan].every(v => uuid.test(v))) return fail(null);
  try {
    const entries = await humanTestFetch<GroupApplicabilityContext[]>(`/investigations/${task}/unit-plans/${plan}/group-rule-contexts`);
    if (!Array.isArray(entries) || entries.some(c => !checkContext(c, task, plan))) throw new Error("Invalid context index");
    return { ok: true, value: entries };
  } catch (error) { return fail(error); }
}
export async function loadGroupApplicabilityAction(i: GroupApplicabilityIdentity, after: string | null = null): Promise<GroupApplicabilityResult<GroupApplicabilityView>> {
  if (!i || ![i.task_id, i.target_plan_id, i.source_rule_preparation_id, i.source_rule_candidate_id].every(v => uuid.test(v))
    || (after !== null && (after.split(":").length !== 2 || !after.split(":").every(v => uuid.test(v))))) return fail(null);
  try {
    const v = await humanTestFetch<GroupApplicabilityView>(`/investigations/${i.task_id}/unit-plans/${i.target_plan_id}/group-rule-applicability/${i.source_rule_preparation_id}/${i.source_rule_candidate_id}${after ? `?${new URLSearchParams({ after })}` : ""}`);
    const c = v.context;
    if (v.scope !== "GROUP_APPLICABILITY_CONTEXT_ONLY" || v.outcome !== "UNDECIDED" || !checkContext(c, i.task_id, i.target_plan_id)
      || c.source_rule_preparation_id !== i.source_rule_preparation_id || c.source_rule_candidate_id !== i.source_rule_candidate_id
      || hash(c) !== v.context_hash || hash(v.source_review) !== c.source_review_hash || hash(v.approval) !== c.source_rule_approval_hash
      || v.approval.decision !== "APPROVE" || v.approval.decision_id !== c.source_rule_approval_id || v.candidate.rule_candidate_id !== c.source_rule_candidate_id
      || hash(v.target_plan.plan) !== c.target_plan_hash || hash(v.target_plan.context) !== c.target_plan_context_hash
      || v.target_plan.plan_id !== i.target_plan_id || stable(v.target_plan.plan.target) !== stable(c.target)
      || v.source_review.preparation_id !== i.source_rule_preparation_id || v.source_review.result_hash !== c.source_rule_preparation_hash
      || stable(v.source_review.decisions[i.source_rule_candidate_id]) !== stable(v.approval)
      || !v.source_review.result.rows.some(row => stable(row) === stable(v.candidate))
      || !Array.isArray(v.evidence_options) || v.evidence_options.length > 50
      || (v.next_cursor !== null && (v.evidence_options.length !== 50 || v.next_cursor !== `${v.evidence_options[49].block_id}:${v.evidence_options[49].member_id}`))) throw new Error("Invalid review context");
    return { ok: true, value: v };
  } catch (error) { return fail(error); }
}
