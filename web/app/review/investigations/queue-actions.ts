"use server";
import { humanTestFetch } from "../../../lib/local-human-test";
import { relationKinds, relationStatus, type RelationResult } from "../../../lib/relation-review";
import type { RelationQueueView } from "../../../lib/relation-queue";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export async function loadRelationQueue(task: string, plan: string, after?: string): Promise<RelationResult<RelationQueueView>> {
  try {
    if (![task, plan, ...(after ? [after] : [])].every(x => uuid.test(x))) throw new Error("Invalid identity");
    const v = await humanTestFetch<RelationQueueView>(`/investigations/${task}/unit-plans/${plan}/relation-queue${after ? `?after=${encodeURIComponent(after)}` : ""}`);
    if (v.task_id !== task || v.target_plan_id !== plan || v.executable !== false || v.overall_qualification !== "UNCERTAIN"
      || !/^[0-9a-f]{64}$/.test(v.source_review_hash) || !Number.isFinite(Date.parse(v.read_at))
      || !Array.isArray(v.proposals) || v.proposals.length > 50
      || v.proposals.some((p, i) => !uuid.test(p.proposal_id) || !Number.isFinite(Date.parse(p.created_at))
        || !Object.hasOwn(relationKinds, p.relation) || !Object.hasOwn(relationStatus, p.status)
        || typeof p.is_own_proposal !== "boolean" || !p.reason.trim() || p.reason.length > 2000
        || !Array.isArray(p.condition_ids) || p.condition_ids.length < 2 || p.condition_ids.some(id => typeof id !== "string" || !id.trim())
        || new Set(p.condition_ids).size !== p.condition_ids.length
        || p.proposal_id <= (i ? v.proposals[i - 1].proposal_id : after ?? ""))
      || (v.next_after !== null && (v.proposals.length !== 50 || v.next_after !== v.proposals.at(-1)?.proposal_id))) throw new Error("Invalid queue");
    return { ok: true, value: v };
  } catch { return { ok: false, error: "当前审核队列读取失败，旧状态已隐藏。请核对权限后重新读取。" }; }
}
