"use server";
import { createHash } from "node:crypto";
import { postInvestigation, InvestigationApiError } from "../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { loadGroupApplicabilityAction } from "./group-applicability-actions";
import type { GroupApplicabilityIdentity, GroupApplicabilityResult } from "../../../lib/group-applicability";
import type { GroupApplicabilityDecision, GroupApplicabilityHistory, GroupApplicabilityRequest, GroupApplicabilityReviewView } from "../../../lib/group-applicability-decisions";
import { applicabilityOutcomes } from "../../../lib/rule-applicability";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function stable(value: unknown): string { return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item); }
function hash(value: unknown) { return createHash("sha256").update(stable(value)).digest("hex"); }
function failure(error: unknown): Exclude<GroupApplicabilityResult<never>, { ok: true }> {
  const status = error instanceof LocalHumanTestApiError || error instanceof InvestigationApiError ? error.status : 0;
  if ([401, 403].includes(status)) return { ok: false, kind: "forbidden", error: "审核权限已失效，旧内容已隐藏。" };
  if ([404, 409].includes(status)) return { ok: false, kind: "stale", error: "来源或上一决定已变化，请重新读取后核对。" };
  return { ok: false, kind: "unavailable", error: "未取得可靠回执，旧内容已隐藏。可重试原请求或重新读取。" };
}
function checkReceipt(d: GroupApplicabilityDecision, i: GroupApplicabilityIdentity) {
  return uuid.test(d.decision_id) && uuid.test(d.reviewer_id) && Number.isInteger(d.sequence) && d.sequence > 0
    && d.request.contract_version === "group-applicability-decision/1.0.0"
    && d.context.task_id === i.task_id && d.context.target_plan_id === i.target_plan_id
    && d.context.source_rule_preparation_id === i.source_rule_preparation_id && d.context.source_rule_candidate_id === i.source_rule_candidate_id
    && d.request.target_plan_id === i.target_plan_id && d.request.source_rule_preparation_id === i.source_rule_preparation_id
    && d.request.source_rule_candidate_id === i.source_rule_candidate_id
    && Object.hasOwn(applicabilityOutcomes, d.request.outcome)
    && hash(d.context) === d.context_hash && hash(d.request) === d.request_hash && hash(d.evidence_snapshot) === d.evidence_hash
    && d.request.context_hash === d.context_hash && Number.isFinite(Date.parse(d.created_at))
    && stable(d.request.evidence) === stable(d.evidence_snapshot.map(({ member_id, block_id, quote }) => ({ member_id, block_id, quote })));
}
export async function loadGroupApplicabilityReview(i: GroupApplicabilityIdentity, after: string | null = null): Promise<GroupApplicabilityResult<GroupApplicabilityReviewView>> {
  const current = await loadGroupApplicabilityAction(i, after);
  if (!current.ok) return current;
  try {
    const history = await humanTestFetch<GroupApplicabilityHistory>(`/investigations/${i.task_id}/unit-plans/${i.target_plan_id}/group-applicability-decisions/${i.source_rule_preparation_id}/${i.source_rule_candidate_id}`);
    if (history.scope !== "GROUP_APPLICABILITY_REVIEW_ONLY" || stable(history.context) !== stable(current.value.context)
      || history.context_hash !== current.value.context_hash || !Array.isArray(history.history)
      || stable(history.latest) !== stable(history.history.at(-1) ?? null)) throw new Error("History mismatch");
    for (const [index, receipt] of history.history.entries()) {
      if (!checkReceipt(receipt, i) || receipt.sequence !== index + 1
        || receipt.request.previous_decision_id !== (history.history[index - 1]?.decision_id ?? null)
        || stable({ ...receipt.context, source_review_hash: null }) !== stable({ ...history.context, source_review_hash: null })) throw new Error("Invalid history");
    }
    return { ok: true, value: { ...current.value, decisions: history } };
  } catch (error) { return failure(error); }
}
export async function saveGroupApplicabilityDecision(i: GroupApplicabilityIdentity, request: GroupApplicabilityRequest, nonce: string): Promise<GroupApplicabilityResult<GroupApplicabilityDecision>> {
  try {
    if (![i.task_id, i.target_plan_id, i.source_rule_preparation_id, i.source_rule_candidate_id, nonce].every(v => uuid.test(v))
      || request.contract_version !== "group-applicability-decision/1.0.0" || request.target_plan_id !== i.target_plan_id
      || request.source_rule_preparation_id !== i.source_rule_preparation_id || request.source_rule_candidate_id !== i.source_rule_candidate_id
      || !/^[a-f0-9]{64}$/.test(request.context_hash) || !(request.previous_decision_id === null || uuid.test(request.previous_decision_id))
      || !Object.hasOwn(applicabilityOutcomes, request.outcome) || !request.reason.trim() || request.reason.length > 2000
      || !Array.isArray(request.evidence) || request.evidence.length > 20 || (request.outcome !== "NEEDS_ADJUDICATION" && !request.evidence.length)
      || request.evidence.some(e => !uuid.test(e.member_id) || !uuid.test(e.block_id) || !e.quote.trim() || e.quote.length > 20000)
      || new Set(request.evidence.map(stable)).size !== request.evidence.length) return { ok: false, kind: "stale", error: "决定、理由或引文不完整，请重新核对。" };
    const path = `/investigations/${i.task_id}/group-applicability-decisions`;
    const receipt = await postInvestigation<GroupApplicabilityDecision>(path, request, hash([nonce, path, request]));
    if (!checkReceipt(receipt, i) || stable(receipt.request) !== stable(request)) throw new Error("Receipt mismatch");
    return { ok: true, value: receipt };
  } catch (error) { return failure(error); }
}
