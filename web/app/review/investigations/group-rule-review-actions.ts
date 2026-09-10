"use server";
import { createHash } from "node:crypto";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { postInvestigation } from "../../../lib/investigations";
import { loadGroupRulePreviewAction } from "./group-rule-actions";
import { evidenceAuthorities, groupRuleReviewVersion, type GroupRuleAssessment, type GroupRuleReviewCommand, type GroupRuleReviewRecord, type GroupRuleReviewResult } from "../../../lib/group-rule-review";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i, sha = /^[a-f0-9]{64}$/;
function stable(value: unknown): string { return JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item); }
function hash(value: unknown) { return createHash("sha256").update(stable(value)).digest("hex"); }
function assessmentSignature(evidence: GroupRuleAssessment[]) { return stable(evidence.map(e => ({ ...e, effective_at: e.effective_at ? new Date(e.effective_at).toISOString() : null, reason: e.reason.trim() })).sort((a, b) => a.evidence_ref_id.localeCompare(b.evidence_ref_id))); }
function mismatch(): never { throw new LocalHumanTestApiError(409); }
const invalid = { ok: false, kind: "invalid", error: "审核请求不完整，请核对候选、每条证据和审核说明。" } as const;
function failure(error: unknown): Exclude<GroupRuleReviewResult, { ok: true }> {
  if (error instanceof LocalHumanTestApiError) {
    if ([401, 403].includes(error.status)) return { ok: false, kind: "forbidden", error: "当前会话无权审核组规则，旧内容已隐藏。" };
    if ([404, 409].includes(error.status)) return { ok: false, kind: "stale", error: "组身份、事实、证据或审核状态已变化，旧内容已隐藏。请重新读取。" };
    if ([400, 422].includes(error.status)) return invalid;
  }
  return { ok: false, kind: "unavailable", error: "暂未取得当前回执，旧内容已隐藏；可明确重试原请求。" };
}
function assessmentValid(e: GroupRuleAssessment) {
  return uuid.test(e.evidence_ref_id) && (e.authority === null || Object.hasOwn(evidenceAuthorities, e.authority))
    && [null, "SUPPORTS", "CONTRADICTS"].includes(e.relation) && ["UNRESOLVED", "APPLIES_TO_EXACT_TARGET"].includes(e.applicability)
    && typeof e.reason === "string" && !!e.reason.trim() && e.reason.length <= 2000
    && (e.effective_at === null || (typeof e.effective_at === "string" && /T.*(Z|[+-]\d{2}:\d{2})$/.test(e.effective_at) && Number.isFinite(Date.parse(e.effective_at))));
}
function check(record: GroupRuleReviewRecord, task: string, id: string) {
  const result = record.result;
  if (record.preparation_id !== id || !uuid.test(id) || !uuid.test(record.fact_preparation_id) || !uuid.test(record.fact_set_id)
    || !uuid.test(record.reviewer_id) || !Number.isFinite(Date.parse(record.created_at)) || hash(result) !== record.result_hash
    || result.contract_version !== groupRuleReviewVersion || result.scope !== "GROUP_RULE_REVIEW_ONLY"
    || result.preview.result.fact_review.result.group_source.source.task_id !== task
    || record.fact_preparation_id !== result.preview.result.fact_review.preparation_id
    || record.fact_set_id !== result.preview.result.fact_review.fact_set?.fact_set_id
    || result.rows.length !== result.preview.result.rows.length) mismatch();
  const candidates = new Map<string, string[]>();
  result.rows.forEach((row, i) => {
    const { rule_candidate_id: id, ...previewRow } = row;
    if (stable(previewRow) !== stable(result.preview.result.rows[i]) || !!id !== !!row.proposed_rule_payload) mismatch();
    if (id) { if (!uuid.test(id) || candidates.has(id)) mismatch(); candidates.set(id, row.evidence_ref_ids); }
  });
  const current: GroupRuleReviewRecord["decisions"] = {}, ids = new Set<string>();
  for (const d of record.history) {
    const refs = candidates.get(d.rule_candidate_id);
    if (!refs || !uuid.test(d.decision_id) || ids.has(d.decision_id) || !uuid.test(d.reviewer_id) || !Number.isFinite(Date.parse(d.created_at))
      || !["APPROVE", "REJECT", "NEEDS_ADJUDICATION"].includes(d.decision) || !d.reason?.trim() || d.reason.length > 2000
      || (current[d.rule_candidate_id] && current[d.rule_candidate_id].decision !== "NEEDS_ADJUDICATION")
      || !Array.isArray(d.evidence) || new Set(d.evidence.map(e => e.evidence_ref_id)).size !== d.evidence.length
      || d.evidence.some(e => !assessmentValid(e) || !refs.includes(e.evidence_ref_id) || (e.effective_at && Date.parse(e.effective_at) > Date.parse(d.created_at)))
      || (d.decision === "APPROVE" && (d.evidence.length !== refs.length || d.evidence.some(e => !e.authority || !e.relation || !e.effective_at || e.applicability !== "APPLIES_TO_EXACT_TARGET")))) mismatch();
    ids.add(d.decision_id); current[d.rule_candidate_id] = d;
  }
  if (stable(current) !== stable(record.decisions)) mismatch();
}
export async function loadGroupRuleReviewAction(task: string, id: string): Promise<GroupRuleReviewResult> {
  if (!uuid.test(task) || !uuid.test(id)) return invalid;
  try {
    const record = await humanTestFetch<GroupRuleReviewRecord>(`/investigations/${task}/group-rules/${id}`);
    check(record, task, id);
    const preview = await loadGroupRulePreviewAction(task, record.fact_preparation_id);
    if (!preview.ok) return preview;
    if (stable(preview.value) !== stable(record.result.preview)) mismatch();
    return { ok: true, value: record };
  } catch (error) { return failure(error); }
}
export async function submitGroupRuleReviewAction(task: string, command: GroupRuleReviewCommand): Promise<GroupRuleReviewResult> {
  if (!uuid.test(task) || !command) return invalid;
  let endpoint: string, body: object;
  if (command.kind === "prepare") {
    if (!uuid.test(command.fact_preparation_id) || !sha.test(command.expected_preview_hash)) return invalid;
    endpoint = `/investigations/${task}/group-facts/${command.fact_preparation_id}/rules`;
    body = { expected_preview_hash: command.expected_preview_hash };
  } else if (command.kind === "decision") {
    if (!uuid.test(command.preparation_id) || !uuid.test(command.rule_candidate_id) || !sha.test(command.expected_preparation_hash)
      || !["APPROVE", "REJECT", "NEEDS_ADJUDICATION"].includes(command.decision) || !command.reason?.trim() || command.reason.length > 2000
      || !Array.isArray(command.evidence) || command.evidence.length > 2000 || !command.evidence.every(assessmentValid)) return invalid;
    endpoint = `/investigations/${task}/group-rules/${command.preparation_id}/decisions`;
    const { kind: _kind, preparation_id: _prep, ...request } = command; void _kind; void _prep;
    body = request;
  } else return invalid;
  try {
    const receipt = await postInvestigation<GroupRuleReviewRecord>(endpoint, body, hash([endpoint, body]));
    check(receipt, task, receipt.preparation_id);
    if (command.kind === "prepare") {
      if (receipt.fact_preparation_id !== command.fact_preparation_id || receipt.result.preview.result_hash !== command.expected_preview_hash) mismatch();
    } else if (receipt.preparation_id !== command.preparation_id || receipt.result_hash !== command.expected_preparation_hash) mismatch();
    const current = await loadGroupRuleReviewAction(task, receipt.preparation_id);
    if (!current.ok) return current;
    if (stable(current.value.result) !== stable(receipt.result)) mismatch();
    if (command.kind === "decision" && !current.value.history.some(d => d.rule_candidate_id === command.rule_candidate_id && d.decision === command.decision && d.reason === command.reason.trim() && assessmentSignature(d.evidence) === assessmentSignature(command.evidence))) mismatch();
    return current;
  } catch (error) { return failure(error); }
}
