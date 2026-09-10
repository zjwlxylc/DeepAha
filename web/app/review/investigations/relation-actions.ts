"use server";
import { createHash } from "node:crypto";
import { canonicalJson as stable } from "../../../lib/cross-level-canonical";
import { humanTestFetch } from "../../../lib/local-human-test";
import { postInvestigation } from "../../../lib/investigations";
import { relationKinds, relationStatus, type RelationIndex, type RelationView, type RelationResult, type RelationDecision } from "../../../lib/relation-review";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const sha = /^[0-9a-f]{64}$/;
const failure = { ok: false as const, error: "未取得有效的当前回执，旧内容已隐藏。请核对权限、重新读取，或重试原请求。" };
function checked(v: RelationView, task: string, plan: string, id: string) {
  const p = v.package.proposal, g = p.source_review.dependencies.group, ds = v.package.decisions;
  if (v.proposal_id !== id || p.proposal_id !== id || v.review.proposal_id !== id
    || g.dependencies.group_source.source.task_id !== task || g.snapshot.base_v2.plan_id !== plan
    || !sha.test(v.proposal_payload_sha256) || !sha.test(v.payload_sha256)
    || !uuid.test(p.producer_id) || !Object.hasOwn(relationKinds, p.relation)
    || !Object.hasOwn(relationStatus, v.review.status) || v.review.executable !== false
    || v.review.overall_qualification !== "UNCERTAIN" || !Array.isArray(p.evidence)
    || stable(v.review.latest) !== stable(ds.at(-1) ?? null)) throw new Error("Invalid view");
  const ids = new Set<string>();
  ds.forEach((d, i) => {
    if (!uuid.test(d.decision_id) || ids.has(d.decision_id) || !uuid.test(d.reviewer_id) || d.reviewer_id === p.producer_id
      || d.proposal_id !== id || d.sequence !== i + 1 || d.previous_decision_id !== (ds[i - 1]?.decision_id ?? null)
      || !["APPROVE", "REJECT", "NEEDS_ADJUDICATION"].includes(d.decision)
      || !d.reason.trim() || !Number.isFinite(Date.parse(d.created_at))) throw new Error("Invalid history");
    ids.add(d.decision_id);
  });
  const latest = ds.at(-1);
  const expected = latest ? ({ APPROVE: "APPROVED", REJECT: "REJECTED", NEEDS_ADJUDICATION: "NEEDS_ADJUDICATION" })[latest.decision] : "UNREVIEWED";
  if (v.review.status !== "STALE" && v.review.status !== expected) throw new Error("Status differs");
  // Frozen hashes are verified by the authenticated backend. JSON.parse loses
  // numeric spelling (1.0 -> 1), so do not recompute full package hashes in JS.
  return v;
}
export async function loadRelationIndex(task: string, plan: string): Promise<RelationResult<RelationIndex>> {
  try {
    if (![task, plan].every(x => uuid.test(x))) throw new Error("Invalid identity");
    const v = await humanTestFetch<RelationIndex>(`/investigations/${task}/unit-plans/${plan}/relation-proposals`);
    if (v.task_id !== task || v.target_plan_id !== plan || !Array.isArray(v.proposals)
      || v.proposals.some(p => !uuid.test(p.proposal_id) || !uuid.test(p.producer_id) || !Number.isFinite(Date.parse(p.created_at)))
      || new Set(v.proposals.map(p => p.proposal_id)).size !== v.proposals.length) throw new Error("Invalid index");
    return { ok: true, value: v };
  } catch { return failure; }
}
export async function loadRelation(task: string, plan: string, id: string): Promise<RelationResult<RelationView>> {
  try {
    if (![task, plan, id].every(x => uuid.test(x))) throw new Error("Invalid identity");
    return { ok: true, value: checked(await humanTestFetch<RelationView>(`/investigations/${task}/relation-proposals/${id}`), task, plan, id) };
  } catch { return failure; }
}
export async function decideRelation(task: string, plan: string, request: { proposal_id: string; expected_proposal_payload_hash: string; previous_decision_id: string | null; decision: RelationDecision["decision"]; reason: string }, nonce: string): Promise<RelationResult<RelationView>> {
  try {
    if (![task, plan, request.proposal_id, nonce].every(x => uuid.test(x)) || !sha.test(request.expected_proposal_payload_hash)
      || (request.previous_decision_id !== null && !uuid.test(request.previous_decision_id))
      || !["APPROVE", "REJECT", "NEEDS_ADJUDICATION"].includes(request.decision) || !request.reason.trim() || request.reason.length > 2000) throw new Error("Invalid request");
    const path = `/investigations/${task}/relation-decisions`;
    // Validate the route's plan before causing any write, including a retry.
    const current = await loadRelation(task, plan, request.proposal_id);
    if (!current.ok) return current;
    const key = createHash("sha256").update(JSON.stringify([path, request, nonce])).digest("hex");
    const receipt = await postInvestigation<RelationView & { decision: RelationDecision }>(path, request, key);
    checked(receipt, task, plan, request.proposal_id);
    const d = receipt.decision;
    if (receipt.proposal_payload_sha256 !== request.expected_proposal_payload_hash || d.decision !== request.decision || d.reason !== request.reason || d.previous_decision_id !== request.previous_decision_id
      || !receipt.package.decisions.some(row => stable(row) === stable(d))) throw new Error("Receipt differs");
    return { ok: true, value: receipt };
  } catch { return failure; }
}
