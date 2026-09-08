"use server";

import { createHash } from "node:crypto";
import { postInvestigation } from "../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { applicabilityOutcomes, applicabilityPath, matchesApplicabilityIdentity, type ApplicabilityDecision, type ApplicabilityIdentity, type ApplicabilityRequest, type ApplicabilityResult, type ApplicabilityView } from "../../../lib/rule-applicability";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[a-f0-9]{64}$/;
function validIdentity(identity: ApplicabilityIdentity) {
  return identity && [identity.task_id, identity.target_plan_id, identity.source_rule_preparation_id, identity.source_rule_candidate_id].every(value => typeof value === "string" && UUID.test(value));
}

function failure(error: unknown): Exclude<ApplicabilityResult<never>, { ok: true }> {
  if (error instanceof LocalHumanTestApiError) {
    if ([401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话没有适用性审阅权限，请使用已授权的审核会话。" };
    if ([404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "来源、岗位或上一决定已变化，或相关规则尚未完成裁决。请重新读取最新状态后核对。" };
    if ([400, 422].includes(error.status)) return { ok: false, kind: "invalid", error: "提交内容不完整，请核对决定、理由及原文引文。" };
  }
  return { ok: false, kind: "unavailable", error: "暂未取得最新回执。可重试原请求，或重新读取最新状态后再修改。" };
}

function requestData(request: ApplicabilityRequest): ApplicabilityRequest {
  return {
    target_plan_id: request.target_plan_id, source_rule_preparation_id: request.source_rule_preparation_id,
    source_rule_candidate_id: request.source_rule_candidate_id, context_hash: request.context_hash,
    previous_decision_id: request.previous_decision_id, outcome: request.outcome,
    evidence: request.evidence.map(({ member_id, block_id, quote }) => ({ member_id, block_id, quote })).sort((a, b) => {
      const left = JSON.stringify(a), right = JSON.stringify(b);
      return left < right ? -1 : left > right ? 1 : 0;
    }), reason: request.reason,
  };
}

export async function saveRuleApplicabilityAction(identity: ApplicabilityIdentity, request: ApplicabilityRequest, nonce: string): Promise<ApplicabilityResult<ApplicabilityDecision>> {
  const invalid = { ok: false, kind: "invalid", error: "请明确选择决定、填写理由，并为适用或不适用选择至少一段当前原文。" } as const;
  if (!validIdentity(identity) || typeof nonce !== "string" || !UUID.test(nonce) || !request
    || request.target_plan_id !== identity.target_plan_id || request.source_rule_preparation_id !== identity.source_rule_preparation_id
    || request.source_rule_candidate_id !== identity.source_rule_candidate_id || !SHA256.test(request.context_hash)
    || !(request.previous_decision_id === null || UUID.test(request.previous_decision_id))
    || !Object.hasOwn(applicabilityOutcomes, request.outcome) || typeof request.reason !== "string"
    || !request.reason.trim() || request.reason.length > 2000 || !Array.isArray(request.evidence)
    || request.evidence.length > 20 || (request.outcome !== "NEEDS_ADJUDICATION" && !request.evidence.length)
    || request.evidence.some(item => !item || !UUID.test(item.member_id) || !UUID.test(item.block_id)
      || typeof item.quote !== "string" || !item.quote.trim() || item.quote.length > 20000)) return invalid;
  const body = requestData(request);
  if (new Set(body.evidence.map(item => JSON.stringify(item))).size !== body.evidence.length) return invalid;
  const path = `/investigations/${identity.task_id}/rule-applicability`;
  const key = createHash("sha256").update(JSON.stringify([nonce, path, body])).digest("hex");
  try {
    const receipt = await postInvestigation<ApplicabilityDecision>(path, body, key);
    if (!UUID.test(receipt.decision_id) || receipt.context_hash !== body.context_hash
      || JSON.stringify(requestData(receipt.request)) !== JSON.stringify(body)) throw new Error("Receipt mismatch");
    return { ok: true, value: receipt };
  } catch (error) { return failure(error); }
}

export async function loadRuleApplicabilityAction(identity: ApplicabilityIdentity, after: string | null = null): Promise<ApplicabilityResult<ApplicabilityView>> {
  if (!validIdentity(identity) || (after !== null && (typeof after !== "string" || !after || after.length > 512))) return { ok: false, kind: "invalid", error: "审阅目标或分页位置不完整，请从当前条件快照重新进入。" };
  try {
    const view = await humanTestFetch<ApplicabilityView>(applicabilityPath(identity) + (after ? `?${new URLSearchParams({ after })}` : ""));
    if (!matchesApplicabilityIdentity(view, identity) || !SHA256.test(view.context_hash)
      || view.source_rule.rule_id !== identity.source_rule_candidate_id) throw new Error("Review context mismatch");
    return { ok: true, value: view };
  } catch (error) { return failure(error); }
}
