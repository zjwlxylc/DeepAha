"use server";

import { createHash } from "node:crypto";
import { loadGroupRecordAction } from "./group-source-actions";
import { groupFactContract, type GroupFactRecord, type GroupFactResult, type GroupFactCommand } from "../../../lib/group-facts";
import { postInvestigation } from "../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import type { GroupSourceData } from "../../../lib/group-sources";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA = /^[a-f0-9]{64}$/;
const invalid = { ok: false, kind: "invalid", error: "组事实审核请求不完整，请从已登记组来源重新进入。" } as const;
function failure(error: unknown): Exclude<GroupFactResult, { ok: true }> {
  if (error instanceof LocalHumanTestApiError) {
    if ([401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话没有组事实审核权限，旧内容已隐藏。" };
    if ([404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "来源、证据、身份或审核状态已变化，旧内容已隐藏。请重新读取当前记录。" };
    if ([400, 422].includes(error.status)) return invalid;
  }
  return { ok: false, kind: "unavailable", error: "暂未取得当前审核记录，旧内容已隐藏。回执丢失时可明确重试原请求。" };
}
function stable(value: unknown): string { return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item); }
function hash(value: unknown) { return createHash("sha256").update(stable(value)).digest("hex"); }
// Task GET restores missing legacy notes for display; the receipt remains frozen.
function withoutDisplayNote<T extends { note?: unknown }>(fact: T) { const copy = { ...fact }; delete copy.note; return copy; }
function mismatch(): never { throw new LocalHumanTestApiError(409); }
function checkRecord(record: GroupFactRecord, source: GroupSourceData, id: string) {
  const result = record.result, task = source.task, group = source.preview.registration;
  if (!group || record.preparation_id !== id || !UUID.test(id) || !SHA.test(record.result_hash)
    || record.result_hash !== hash(result) || result.contract_version !== groupFactContract || result.scope !== "GROUP_FACT_REVIEW_ONLY"
    || stable(result.group_source) !== stable(group) || result.check_id !== task.evidence_check?.check_id
    || result.source_row_count !== task.facts.length || result.check_hash !== task.evidence_check?.result_hash
    || !UUID.test(record.reviewer_id) || !Number.isFinite(Date.parse(record.created_at))) mismatch();
  const entityId = group.source.source_group.id;
  const indexes = task.facts.flatMap((fact, index) => fact.entity_id === entityId ? [index] : []);
  const excludedIndexes = task.facts.flatMap((fact, index) => fact.entity_id !== entityId ? [index] : []);
  if (stable(result.rows.map(row => row.source_index)) !== stable(indexes) || stable(result.excluded_rows.map(row => row.source_index)) !== stable(excludedIndexes)) mismatch();
  for (const row of result.excluded_rows) {
    const fact = task.facts[row.source_index];
    if (row.entity_id !== fact.entity_id || row.reason !== "DIFFERENT_ENTITY_SCOPE"
      || ![hash(fact), hash(withoutDisplayNote(fact))].includes(row.source_hash)) mismatch();
  }
  for (const row of result.rows) {
    const displayed = task.facts[row.source_index];
    if (stable(row.original) !== stable(Object.hasOwn(row.original, "note") ? displayed : withoutDisplayNote(displayed)) || row.entity_id !== entityId
      || row.mapping_version !== groupFactContract || row.target_scope !== "UNIT" || row.original_field !== row.original.field
      || row.raw_value !== row.original.value || row.original_status !== row.original.status
      || row.ready_for_persistence !== !!row.candidate_id || (row.candidate_id !== null && !UUID.test(row.candidate_id))
      || (row.abstained && row.normalized_value_candidate !== null) || row.evidence.length !== row.original.evidence.length) mismatch();
    row.evidence.forEach((e, index) => {
      const expected = task.evidence_check!.references.find(ref => ref.fact_index === row.source_index && ref.reference_index === index);
      if (stable(e.reference) !== stable(row.original.evidence[index]) || stable(e.check_reference) !== stable(expected)
        || (e.binding && (e.binding.block_id !== expected?.persistent_binding?.block_id || e.binding.evidence_ref_id !== expected?.persistent_binding?.evidence_ref_id))
        || (e.check_reference.verdict !== "PASS" && e.binding !== null)
        || (row.candidate_id && (!e.binding || e.check_reference.verdict !== "PASS"))) mismatch();
    });
  }
  const candidates = result.rows.flatMap(row => row.candidate_id ? [row.candidate_id] : []);
  if (new Set(candidates).size !== candidates.length || (!!candidates.length !== !!result.extraction_run_id)) mismatch();
  for (const [id, d] of Object.entries(record.decisions)) {
    if (!candidates.includes(id) || d.candidate_id !== id || !UUID.test(d.decision_id) || !UUID.test(d.reviewer_id)
      || !["APPROVE", "REJECT", "UNKNOWN", "NEEDS_ADJUDICATION"].includes(d.decision) || !d.reason
      || !record.history.some(item => stable(item) === stable(d))) mismatch();
  }
  if (record.fact_set && (!UUID.test(record.fact_set.fact_set_id) || !Number.isInteger(record.fact_set.version)
    || !candidates.length || candidates.some(id => !record.decisions[id] || record.decisions[id].decision === "NEEDS_ADJUDICATION")
    || !Object.values(record.decisions).some(d => ["APPROVE", "UNKNOWN"].includes(d.decision)))) mismatch();
}
export async function loadGroupFactStartAction(taskId: string, groupId: string): Promise<GroupFactResult> {
  const source = await loadGroupRecordAction(taskId, groupId);
  if (!source.ok) return source;
  if (!source.value.task.evidence_check) return { ok: false, kind: "stale", error: "尚无当前证据核验回执，请先返回调查任务准备文档与证据。" };
  return { ok: true, value: { source: source.value, record: null } };
}
export async function loadGroupFactRecordAction(taskId: string, prepId: string): Promise<GroupFactResult> {
  if (!UUID.test(taskId) || !UUID.test(prepId)) return invalid;
  try {
    const record = await humanTestFetch<GroupFactRecord>(`/investigations/${taskId}/group-facts/${prepId}`);
    const source = await loadGroupRecordAction(taskId, record.result.group_source.group_binding_id);
    if (!source.ok) return source;
    checkRecord(record, source.value, prepId);
    return { ok: true, value: { source: source.value, record } };
  } catch (error) { return failure(error); }
}
export async function submitGroupFactAction(taskId: string, command: GroupFactCommand): Promise<GroupFactResult> {
  if (!UUID.test(taskId) || !command || !["prepare", "decision", "promote"].includes(command.kind)) return invalid;
  let endpoint: string, body: object;
  if (command.kind === "prepare") {
    if (!UUID.test(command.group_binding_id) || !UUID.test(command.check_id) || !SHA.test(command.expected_source_hash)) return invalid;
    endpoint = `/investigations/${taskId}/group-bindings/${command.group_binding_id}/facts`;
    body = { check_id: command.check_id, expected_source_hash: command.expected_source_hash };
  } else {
    if (!UUID.test(command.preparation_id) || !SHA.test(command.expected_preparation_hash) || typeof command.reason !== "string" || !command.reason.trim() || command.reason.length > 2000) return invalid;
    endpoint = `/investigations/${taskId}/group-facts/${command.preparation_id}/${command.kind === "decision" ? "decisions" : "promotions"}`;
    body = { expected_preparation_hash: command.expected_preparation_hash, reason: command.reason };
    if (command.kind === "decision") {
      if (!UUID.test(command.candidate_id) || !["APPROVE", "REJECT", "UNKNOWN", "NEEDS_ADJUDICATION"].includes(command.decision)
        || !["SUPPORTED", "UNSUPPORTED", "UNKNOWN"].includes(command.evidence_support) || !["PASSED", "FAILED", "UNKNOWN"].includes(command.precedence_check)) return invalid;
      body = { ...body, candidate_id: command.candidate_id, decision: command.decision, evidence_support: command.evidence_support, precedence_check: command.precedence_check };
    }
  }
  try {
    const receipt = await postInvestigation<GroupFactRecord>(endpoint, body, hash([endpoint, body]));
    if (!UUID.test(receipt.preparation_id) || (command.kind !== "prepare" && receipt.preparation_id !== command.preparation_id)) mismatch();
    const current = await loadGroupFactRecordAction(taskId, receipt.preparation_id);
    if (!current.ok) return current;
    checkRecord(receipt, current.value.source, receipt.preparation_id);
    if (stable(current.value.record?.result) !== stable(receipt.result)) mismatch();
    if (command.kind === "prepare") {
      if (receipt.result.group_source.group_binding_id !== command.group_binding_id || receipt.result.check_id !== command.check_id || receipt.result.group_source.source_hash !== command.expected_source_hash) mismatch();
    } else if (receipt.result_hash !== command.expected_preparation_hash) mismatch();
    if (command.kind === "decision" && !current.value.record!.history.some(d => d.candidate_id === command.candidate_id && d.decision === command.decision && d.reason === command.reason)) mismatch();
    if (command.kind === "promote" && (!current.value.record!.fact_set || current.value.record!.fact_set.reason !== command.reason)) mismatch();
    return current;
  } catch (error) { return failure(error); }
}
