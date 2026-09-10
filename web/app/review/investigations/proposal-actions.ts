"use server";
import { createHash } from "node:crypto";
import { humanTestFetch } from "../../../lib/local-human-test";
import { postInvestigation } from "../../../lib/investigations";
import { canonicalJson } from "../../../lib/cross-level-canonical";
import type { ProposalContext, ProposalRequest } from "../../../lib/relation-proposal";
import type { RelationResult, RelationView } from "../../../lib/relation-review";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const sha = /^[0-9a-f]{64}$/;
const failure = { ok: false as const, error: "未取得有效回执。请核对权限、来源和逐字证据；回执未知时可重试原请求，也可到已保存提案列表核对。" };
export async function loadProposalContext(task: string, plan: string, after?: string): Promise<RelationResult<ProposalContext>> {
  try {
    if (![task, plan].every(x => uuid.test(x))) throw new Error("Invalid identity");
    const v = await humanTestFetch<ProposalContext>(`/investigations/${task}/unit-plans/${plan}/relation-proposal-context${after ? `?after=${encodeURIComponent(after)}` : ""}`);
    const g = v.review.dependencies.group;
    if (v.task_id !== task || v.target_plan_id !== plan || !sha.test(v.review_hash)
      || g.dependencies.group_source.source.task_id !== task || g.snapshot.base_v2.plan_id !== plan
      || v.review.snapshot.executable !== false || v.review.snapshot.overall_qualification !== "UNCERTAIN"
      || !Array.isArray(v.evidence_options) || v.evidence_options.some(e => !uuid.test(e.member_id) || !uuid.test(e.block_id) || typeof e.text !== "string")
      || (v.next_cursor !== null && !v.next_cursor.split(":").every(x => uuid.test(x)))) throw new Error("Invalid context");
    return { ok: true, value: v };
  } catch { return failure; }
}
export async function proposeRelation(task: string, plan: string, input: ProposalRequest, nonce: string): Promise<RelationResult<RelationView>> {
  try {
    if (!uuid.test(nonce) || input.target_plan_id !== plan) return failure;
    const current = await loadProposalContext(task, plan);
    if (!current.ok) return current;
    if (input.expected_review_hash !== current.value.review_hash) return { ok: false, error: "来源已变化，请重新读取当前条件后新建提案。旧请求不会套用新来源。" };
    // Copy only the public command fields; identities and bound evidence belong to the API.
    const request: ProposalRequest = { target_plan_id: plan, expected_review_hash: current.value.review_hash,
      condition_ids: input.condition_ids, relation: input.relation, displaced_condition_ids: input.displaced_condition_ids, reason: input.reason,
      evidence: input.evidence.map(e => ({ member_id: e.member_id, block_id: e.block_id, quote: e.quote, purpose: e.purpose, condition_ids: e.condition_ids })) };
    const path = `/investigations/${task}/relation-proposals`;
    const key = createHash("sha256").update(canonicalJson([path, request, nonce])).digest("hex");
    const v = await postInvestigation<RelationView>(path, request, key);
    const p = v.package.proposal as RelationView["package"]["proposal"] & { source_review_hash: string };
    if (!uuid.test(v.proposal_id) || p.proposal_id !== v.proposal_id || v.review.proposal_id !== v.proposal_id
      || !sha.test(v.proposal_payload_sha256) || !sha.test(v.payload_sha256)
      || p.source_review_hash !== request.expected_review_hash || !uuid.test(p.producer_id)
      || p.source_review.dependencies.group.snapshot.base_v2.plan_id !== plan
      || p.source_review.dependencies.group.dependencies.group_source.source.task_id !== task
      || v.review.executable !== false || v.review.overall_qualification !== "UNCERTAIN"
      || ["condition_ids", "relation", "displaced_condition_ids", "reason"].some(k => canonicalJson(p[k as keyof typeof p]) !== canonicalJson(request[k as keyof ProposalRequest]))
      || canonicalJson(p.evidence.map(e => { const r = e as unknown as ProposalRequest["evidence"][number]; return { member_id: r.member_id, block_id: r.block_id, quote: r.quote, purpose: r.purpose, condition_ids: r.condition_ids }; })) !== canonicalJson(request.evidence)) throw new Error("Receipt differs");
    return { ok: true, value: v };
  } catch { return failure; }
}
