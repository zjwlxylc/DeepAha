"use server";

import { createHash } from "node:crypto";
import { announcementSnapshotAdapter, announcementSnapshotContract, type AnnouncementSnapshotIdentity, type AnnouncementSnapshotInput, type AnnouncementSnapshotRecord, type AnnouncementSnapshotResult } from "../../../lib/announcement-snapshots";
import { getInvestigation, postInvestigation, type InvestigationTask } from "../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { currentSnapshotSource } from "../../../lib/unit-snapshots";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA = /^[a-f0-9]{64}$/;
const invalid = { ok: false, kind: "invalid", error: "快照标识或依赖摘要不完整，请从当前基础快照重新进入。" } as const;
function failure(error: unknown): Exclude<AnnouncementSnapshotResult, { ok: true }> {
  if (error instanceof LocalHumanTestApiError) {
    if ([401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话没有查看或保存权限，请使用已授权的审核会话。" };
    if ([404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "来源、适用性决定或岗位版本已变化，或该记录不属于当前目标。旧内容已隐藏，请重新获取当前输入。" };
  }
  return { ok: false, kind: "unavailable", error: "暂时未取得当前快照。旧内容已隐藏；保存回执丢失时可重试原摘要，或重新获取当前输入。" };
}
function stable(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item);
}
function mismatch(): never { throw new LocalHumanTestApiError(409); }
function checkInput(input: AnnouncementSnapshotInput, identity: AnnouncementSnapshotIdentity, task?: InvestigationTask) {
  const { snapshot, dependencies: dep } = input, base = snapshot.base_v2;
  if (snapshot.scope !== "DERIVED_SCOPE_SNAPSHOT_ONLY" || snapshot.overall_qualification !== "UNCERTAIN"
    || snapshot.contract_version !== announcementSnapshotContract || snapshot.adapter_version !== announcementSnapshotAdapter
    || dep.contract_version !== announcementSnapshotContract || dep.adapter_version !== announcementSnapshotAdapter
    || !SHA.test(input.dependencies_hash) || dep.base_plan_id !== identity.base_plan_id || base.plan_id !== identity.base_plan_id
    || dep.base_plan_hash !== base.plan_hash || dep.base_context_hash !== base.context_hash
    || dep.fact_preparation_id !== base.plan.manifest.preparation_id || dep.fact_preparation_hash !== base.plan.manifest.preparation_sha256
    || (task && (task.task_id !== identity.task_id || !currentSnapshotSource(base, task)))) mismatch();
  const originals = base.plan.manifest.conditions.filter(row => row.scope === "ANNOUNCEMENT");
  if (originals.length !== snapshot.announcement_conditions.length
    || new Set(snapshot.announcement_conditions.map(row => row.condition.condition_id)).size !== originals.length) mismatch();
  for (const row of snapshot.announcement_conditions) {
    if (!originals.some(original => stable(original) === stable(row.condition)) || !["INHERITED", "EXCLUDED", "UNRESOLVED"].includes(row.disposition)) mismatch();
    const app = row.applicability;
    if (app && (app.context.target_plan_id !== identity.base_plan_id || app.request.target_plan_id !== identity.base_plan_id
      || stable(app.context.target) !== stable(base.plan.target) || app.context_hash !== app.request.context_hash
      || !row.source_rule || row.source_rule.rule_id !== app.context.source_rule_candidate_id || row.source_rule.rule_id !== app.request.source_rule_candidate_id
      || !row.source_rule_approval || row.source_rule_approval.decision_id !== app.context.source_rule_approval_id
      || row.source_rule_approval.rule_candidate_id !== row.source_rule.rule_id
      || row.source_rule_approval.rule_preparation_id !== app.context.source_rule_preparation_id
      || app.request.source_rule_preparation_id !== app.context.source_rule_preparation_id)) mismatch();
    if (row.disposition !== "UNRESOLVED" && (!row.source_fact || !row.source_rule || !row.source_rule_approval
      || row.source_rule_approval.request.decision !== "APPROVE" || !app
      || app.request.outcome !== (row.disposition === "INHERITED" ? "APPLIES" : "DOES_NOT_APPLY"))) mismatch();
  }
}
function checkRecord(record: AnnouncementSnapshotRecord, identity: AnnouncementSnapshotIdentity, id?: string, hash?: string) {
  checkInput(record, identity);
  if (!UUID.test(record.snapshot_id) || (id && record.snapshot_id !== id) || (hash && record.dependencies_hash !== hash)
    || record.base_plan_id !== identity.base_plan_id || !SHA.test(record.snapshot_hash)
    || record.contract_version !== announcementSnapshotContract || record.adapter_version !== announcementSnapshotAdapter) mismatch();
}
function path(identity: AnnouncementSnapshotIdentity) { return `/investigations/${identity.task_id}/unit-plans/${identity.base_plan_id}`; }

export async function loadAnnouncementPreviewAction(identity: AnnouncementSnapshotIdentity): Promise<AnnouncementSnapshotResult> {
  if (!identity || !UUID.test(identity.task_id) || !UUID.test(identity.base_plan_id)) return invalid;
  try {
    const [input, task] = await Promise.all([humanTestFetch<AnnouncementSnapshotInput>(`${path(identity)}/announcement-snapshot-input`), getInvestigation(identity.task_id)]);
    checkInput(input, identity, task);
    return { ok: true, value: { task, input, record: null } };
  } catch (error) { return failure(error); }
}
export async function loadAnnouncementRecordAction(taskId: string, snapshotId: string): Promise<AnnouncementSnapshotResult> {
  if (!UUID.test(taskId) || !UUID.test(snapshotId)) return invalid;
  try {
    const [record, task] = await Promise.all([humanTestFetch<AnnouncementSnapshotRecord>(`/investigations/${taskId}/announcement-snapshots/${snapshotId}`), getInvestigation(taskId)]);
    const identity = { task_id: taskId, base_plan_id: record.base_plan_id };
    checkRecord(record, identity, snapshotId); checkInput(record, identity, task);
    const input = { dependencies: record.dependencies, dependencies_hash: record.dependencies_hash, snapshot: record.snapshot };
    return { ok: true, value: { task, input, record } };
  } catch (error) { return failure(error); }
}
export async function saveAnnouncementSnapshotAction(identity: AnnouncementSnapshotIdentity, hash: string): Promise<AnnouncementSnapshotResult> {
  if (!identity || !UUID.test(identity.task_id) || !UUID.test(identity.base_plan_id) || !SHA.test(hash)) return invalid;
  try {
    const endpoint = `${path(identity)}/announcement-snapshots`;
    const key = createHash("sha256").update(JSON.stringify([endpoint, hash])).digest("hex");
    const receipt = await postInvestigation<AnnouncementSnapshotRecord>(endpoint, { expected_dependencies_hash: hash }, key);
    checkRecord(receipt, identity, undefined, hash);
    const current = await loadAnnouncementRecordAction(identity.task_id, receipt.snapshot_id);
    if (!current.ok) return current;
    if (!current.value.record) mismatch();
    checkRecord(current.value.record, identity, receipt.snapshot_id, hash);
    if (current.value.record.snapshot_hash !== receipt.snapshot_hash) mismatch();
    return current;
  } catch (error) { return failure(error); }
}
