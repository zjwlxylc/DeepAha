import type { InvestigationUnitSnapshot } from "./unit-snapshots";
import { relationKinds, relationStatus } from "./relation-review";
export const scopeLabels = { UNIT: "岗位条件", ANNOUNCEMENT: "公告条件", EMPLOYER_GROUP: "单位组条件" };
export const scopeDispositions = { LOCAL: "岗位原生条件", INHERITED: "已纳入继承范围", EXCLUDED: "已明确不适用", UNRESOLVED: "适用范围待处理" };
export const timeLabels = { NOT_YET_VALID: "尚未生效", EXPIRED: "已过期", END_NOT_ESTABLISHED: "结束时间尚未建立，不能视为永久有效", WITHIN_RECORDED_INTERVAL: "在记录的有效期内，仍需完整范围审核" };
export const scopeIssues: Record<string, string> = {
  HUMAN_SCOPE_REVIEW_UNVERIFIED: "完整条件范围尚未独立审核",
  SCOPE_PREFLIGHT_REVIEW_ONLY: "本结果仅供预检，不能执行资格裁决",
  EVIDENCE_TIME_BOUNDARIES_NOT_ESTABLISHED: "证据时间边界尚未建立",
  INHERITED_TIME_BOUNDARIES_NOT_REVIEWED: "继承条件的有效期尚未审核",
  CROSS_LEVEL_SEMANTICS_NOT_REVIEWED: "跨层条件含义尚未完成整体验证",
  CROSS_LEVEL_RELATION_COVERAGE_INCOMPLETE: "仍有跨层条件对缺少当前有效的关系审阅",
  OVERLAPPING_RELATIONS_REQUIRE_REVIEW: "多个已批准关系交叠，需要共同审核",
  CROSS_LEVEL_CONFLICT_RECORDED: "已记录条件冲突，仍需解决",
  EXCEPTION_EXECUTION_NOT_IMPLEMENTED: "例外关系尚不能进入资格执行",
  APPLICABILITY_UNRESOLVED: "适用范围仍待处理",
  CONDITION_UNKNOWN: "条件信息不足", CONDITION_UNPROCESSED: "条件尚未处理",
  CONDITION_CONFLICT: "条件存在冲突", CONDITION_UNSUPPORTED: "条件暂不能形成规则",
  CONDITION_REJECTED: "条件候选被拒绝，仍需核对", CONDITION_UNLOCATED: "条件证据尚未定位",
};
export interface ScopePreflightView {
  contract_version: "unit-scope-preflight/1.0.0"; task_id: string; target_plan_id: string;
  source_review_hash: string; as_of: string; target: InvestigationUnitSnapshot["plan"]["target"];
  source_row_count: number; executable: false; overall_qualification: "UNCERTAIN";
  conditions: { condition_id: string; scope: keyof typeof scopeLabels; field_name: string; state: string;
    disposition: keyof typeof scopeDispositions; source_pointer: string; issues: string[] }[];
  excluded_source_rows: InvestigationUnitSnapshot["context"]["excluded_source_rows"];
  source_notes: { condition_id: string; note: string }[];
  unresolved_source_references: unknown[];
  relations: { proposal_id: string; status: keyof typeof relationStatus; relation: string; condition_ids: string[]; payload_sha256: string }[];
  uncovered_condition_pairs: string[][]; overlapping_relation_pairs: string[][];
  local_evidence_validity: { rule_id: string; evidence_ref_id: string; valid_from: string; valid_until: string | null; status: keyof typeof timeLabels }[];
  local_kernel_blockers: { code: string; condition_id: string | null; rule_id: string | null }[];
  blockers: string[];
}
export const scopeUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const hash = /^[0-9a-f]{64}$/;
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === "string" && !!x.trim());
const instant = (v: string) => typeof v === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
export function validScopePreflight(v: ScopePreflightView, task: string, plan: string): boolean {
  if (v.task_id !== task || v.target_plan_id !== plan || v.contract_version !== "unit-scope-preflight/1.0.0"
    || v.executable !== false || v.overall_qualification !== "UNCERTAIN" || !hash.test(v.source_review_hash) || !instant(v.as_of)
    || !Array.isArray(v.conditions) || !Array.isArray(v.excluded_source_rows)
    || !Number.isSafeInteger(v.source_row_count) || v.source_row_count < 0
    || v.source_row_count !== v.conditions.length + v.excluded_source_rows.length
    || !strings(v.blockers) || !v.blockers.includes("HUMAN_SCOPE_REVIEW_UNVERIFIED") || !v.blockers.includes("SCOPE_PREFLIGHT_REVIEW_ONLY")) return false;
  const ids = new Set(v.conditions.map(c => c.condition_id));
  const target = v.target;
  if (![target.opportunity_id, target.unit_id, target.unit_version_id].every(id => scopeUuid.test(id))
    || ![target.opportunity_version, target.unit_version].every(n => Number.isSafeInteger(n) && n > 0)
    || ids.size !== v.conditions.length || v.conditions.some(c => !strings([c.condition_id, c.field_name, c.source_pointer])
      || !Object.hasOwn(scopeLabels, c.scope) || !Object.hasOwn(scopeDispositions, c.disposition)
      || !["KNOWN", "UNKNOWN", "CONFLICT", "UNSUPPORTED", "REJECTED", "UNLOCATED", "UNPROCESSED"].includes(c.state) || !strings(c.issues))) return false;
  if (!Array.isArray(v.relations) || v.relations.length > 200 || new Set(v.relations.map(r => r.proposal_id)).size !== v.relations.length
    || v.relations.some(r => !scopeUuid.test(r.proposal_id) || !Object.hasOwn(relationStatus, r.status) || !Object.hasOwn(relationKinds, r.relation)
      || !hash.test(r.payload_sha256) || !strings(r.condition_ids) || r.condition_ids.length < 2 || new Set(r.condition_ids).size !== r.condition_ids.length)) return false;
  // Stale proposals can reference previous conditions; current approvals cannot.
  if (v.relations.some(r => r.status !== "STALE" && r.condition_ids.some(id => !ids.has(id)))) return false;
  const proposals = new Set(v.relations.map(r => r.proposal_id));
  const pairs = (values: string[][], allowed: Set<string>) => Array.isArray(values) && values.every(p => strings(p) && p.length === 2 && p[0] !== p[1] && p.every(id => allowed.has(id)));
  return pairs(v.uncovered_condition_pairs, ids) && pairs(v.overlapping_relation_pairs, proposals)
    && Array.isArray(v.source_notes) && v.source_notes.every(n => ids.has(n.condition_id) && typeof n.note === "string")
    && Array.isArray(v.unresolved_source_references)
    && Array.isArray(v.local_kernel_blockers) && v.local_kernel_blockers.every(b => strings([b.code]) && (b.condition_id === null || ids.has(b.condition_id)) && (b.rule_id === null || scopeUuid.test(b.rule_id)))
    && Array.isArray(v.local_evidence_validity) && v.local_evidence_validity.every(e => scopeUuid.test(e.rule_id) && scopeUuid.test(e.evidence_ref_id)
      && instant(e.valid_from) && (e.valid_until === null || (instant(e.valid_until) && Date.parse(e.valid_until) > Date.parse(e.valid_from)))
      && Object.hasOwn(timeLabels, e.status)
      && e.status === (Date.parse(v.as_of) < Date.parse(e.valid_from) ? "NOT_YET_VALID"
        : e.valid_until !== null && Date.parse(v.as_of) >= Date.parse(e.valid_until) ? "EXPIRED"
          : e.valid_until === null ? "END_NOT_ESTABLISHED" : "WITHIN_RECORDED_INTERVAL"));
}
export function scopePreflightPath(task: string, plan: string) {
  return `/review/investigations/${encodeURIComponent(task)}/unit-plans/${encodeURIComponent(plan)}/scope-preflight`;
}
