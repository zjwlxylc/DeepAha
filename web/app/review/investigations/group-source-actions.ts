"use server";

import { createHash } from "node:crypto";
import { groupContract, groupScope, type GroupSourceIdentity, type GroupSource, type GroupSourceRecord, type GroupSourcePreview, type GroupSourceResult } from "../../../lib/group-sources";
import { getInvestigation, postInvestigation, type InvestigationTask } from "../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA = /^[a-f0-9]{64}$/;
const invalid = { ok: false, kind: "invalid", error: "组来源标识不完整，请从当前调查任务重新进入。" } as const;
function valid(identity: GroupSourceIdentity) { return identity && UUID.test(identity.task_id) && typeof identity.entity_id === "string" && identity.entity_id.length > 0 && identity.entity_id.length <= 256; }
function failure(error: unknown): Exclude<GroupSourceResult, { ok: true }> {
  if (error instanceof LocalHumanTestApiError) {
    if ([401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话没有查看或登记权限，旧内容已隐藏。请使用已授权的审核会话。" };
    if ([404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "来源、成员或版本已变化，或记录不属于当前任务。旧内容已隐藏，请返回任务读取当前组来源。" };
  }
  return { ok: false, kind: "unavailable", error: "暂未取得当前组来源，旧内容已隐藏。登记回执丢失时可重试原摘要，或重新读取当前输入。" };
}
function mismatch(): never { throw new LocalHumanTestApiError(409); }
function stable(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item);
}
function checkSource(source: GroupSource, identity: GroupSourceIdentity, task: InvestigationTask) {
  const binding = task.entity_binding;
  const groups = task.opportunities?.units;
  if (!binding || task.status !== "APPROVED" || binding.bundle_status !== "FROZEN" || !Array.isArray(groups)
    || task.task_id !== identity.task_id || source.task_id !== identity.task_id
    || source.contract_version !== groupContract || source.scope !== groupScope
    || source.delivery_hash !== task.delivery_hash || source.binding_id !== binding.binding_id
    || source.opportunity_id !== binding.opportunity_id || source.opportunity_version !== binding.opportunity_version
    || source.source_bundle_revision_id !== binding.source_bundle_revision_id || source.canonical_bundle_hash !== binding.canonical_bundle_hash
    || ![source.delivery_hash, source.binding_hash, source.canonical_bundle_hash, source.source_snapshot_hash].every(hash => SHA.test(hash))
    || source.source_group.id !== identity.entity_id || source.source_entity.id !== identity.entity_id || source.source_entity.kind !== "unit"
    || !task.binding_entities?.some(entity => entity.id === identity.entity_id && entity.kind === "unit")
    || groups.filter(group => group.id === identity.entity_id).length !== 1
    || stable(groups.find(group => group.id === identity.entity_id)) !== stable(source.source_group)) mismatch();
  const ids = source.source_group.positions.map(row => row.id);
  if (new Set(ids).size !== ids.length || stable(source.members.map(row => row.entity_id)) !== stable(ids)) mismatch();
  for (const member of source.members) {
    const matches = binding.positions.filter(position => position.entity_id === member.entity_id);
    if (matches.length > 1 || member.state !== (matches.length ? "BOUND" : "UNPROCESSED")
      || stable(member.position_binding) !== stable(matches[0] ?? null)) mismatch();
  }
  const status = !ids.length ? "NO_MEMBERS" : source.members.some(row => row.state === "UNPROCESSED") ? "UNPROCESSED_MEMBERS" : "ALL_MEMBERS_BOUND";
  if (source.membership_status !== status) mismatch();
}
function checkRecord(record: GroupSourceRecord, identity: GroupSourceIdentity, task: InvestigationTask, id?: string, hash?: string) {
  checkSource(record.source, identity, task);
  const group = record.group_identity;
  if (record.contract_version !== groupContract || record.scope !== groupScope || !UUID.test(record.group_binding_id)
    || (id && record.group_binding_id !== id) || !SHA.test(record.source_hash) || (hash && record.source_hash !== hash)
    || group.unit_kind !== "GROUP" || !UUID.test(group.unit_id) || !UUID.test(group.unit_version_id)
    || group.public_id !== `unit_${group.unit_id.replaceAll("-", "")}` || !Number.isInteger(group.version) || group.version < 1
    || !group.key || !group.label || !UUID.test(record.reviewer_id) || !Number.isFinite(Date.parse(record.created_at))) mismatch();
}
export async function loadGroupPreviewAction(identity: GroupSourceIdentity): Promise<GroupSourceResult> {
  if (!valid(identity)) return invalid;
  try {
    const [preview, task] = await Promise.all([humanTestFetch<GroupSourcePreview>(`/investigations/${identity.task_id}/group-source-input?entity_id=${encodeURIComponent(identity.entity_id)}`), getInvestigation(identity.task_id)]);
    checkSource(preview.source, identity, task);
    if (!SHA.test(preview.source_hash) || (preview.existing_group_id !== null && !UUID.test(preview.existing_group_id))) mismatch();
    if (preview.registration) {
      checkRecord(preview.registration, identity, task, undefined, preview.source_hash);
      if (preview.existing_group_id !== preview.registration.group_identity.unit_id || stable(preview.registration.source) !== stable(preview.source)) mismatch();
    }
    return { ok: true, value: { task, preview } };
  } catch (error) { return failure(error); }
}
export async function loadGroupRecordAction(taskId: string, recordId: string): Promise<GroupSourceResult> {
  if (!UUID.test(taskId) || !UUID.test(recordId)) return invalid;
  try {
    const [record, task] = await Promise.all([humanTestFetch<GroupSourceRecord>(`/investigations/${taskId}/group-bindings/${recordId}`), getInvestigation(taskId)]);
    const identity = { task_id: taskId, entity_id: record.source.source_group.id };
    checkRecord(record, identity, task, recordId);
    return { ok: true, value: { task, preview: { source: record.source, source_hash: record.source_hash, existing_group_id: record.group_identity.unit_id, registration: record } } };
  } catch (error) { return failure(error); }
}
export async function saveGroupSourceAction(identity: GroupSourceIdentity, hash: string): Promise<GroupSourceResult> {
  if (!valid(identity) || !SHA.test(hash)) return invalid;
  try {
    const endpoint = `/investigations/${identity.task_id}/group-bindings`;
    const key = createHash("sha256").update(JSON.stringify([endpoint, identity.entity_id, hash])).digest("hex");
    const receipt = await postInvestigation<GroupSourceRecord>(endpoint, { entity_id: identity.entity_id, expected_source_hash: hash }, key);
    if (!UUID.test(receipt.group_binding_id) || receipt.source_hash !== hash || receipt.source.task_id !== identity.task_id || receipt.source.source_group.id !== identity.entity_id) mismatch();
    const current = await loadGroupRecordAction(identity.task_id, receipt.group_binding_id);
    if (!current.ok) return current;
    checkRecord(receipt, identity, current.value.task, receipt.group_binding_id, hash);
    if (stable(current.value.preview.registration) !== stable(receipt)) mismatch();
    return current;
  } catch (error) { return failure(error); }
}
