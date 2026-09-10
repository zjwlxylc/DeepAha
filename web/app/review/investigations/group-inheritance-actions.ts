"use server";
import { createHash } from "node:crypto";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { inheritanceVersion, type GroupInheritance, type GroupInheritanceResult } from "../../../lib/group-inheritance";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function stable(v: unknown): string { return JSON.stringify(v, (_k, x: unknown) => x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : x); }
function hash(v: unknown) { return createHash("sha256").update(stable(v)).digest("hex"); }
export async function loadGroupInheritanceAction(task: string, plan: string): Promise<GroupInheritanceResult> {
  try {
    if (![task, plan].every(v => uuid.test(v))) throw new Error("Invalid identity");
    const v = await humanTestFetch<GroupInheritance>(`/investigations/${task}/unit-plans/${plan}/group-inheritance-preview`);
    const d = v.dependencies, s = v.snapshot, base = d.base_v2, g = d.group_source;
    const conditions = base.plan.manifest.conditions.filter(c => c.scope === "EMPLOYER_GROUP");
    const originals = (g.source.source_group.unit_level ?? []) as { field: string; value: string | null; status: string; note?: string | null; evidence?: { artifact_id: string; quote: string; locator: unknown }[] }[];
    if (d.contract_version !== inheritanceVersion || s.contract_version !== inheritanceVersion
      || s.scope !== "GROUP_INHERITANCE_PREVIEW_ONLY" || s.overall_qualification !== "UNCERTAIN"
      || hash(d) !== v.dependencies_hash || hash(s) !== v.snapshot_hash || stable(base) !== stable(s.base_v2)
      || base.plan_id !== plan || base.plan.qualification_plan_id !== plan || g.source.task_id !== task
      || hash(base.plan) !== base.plan_hash || hash(base.context) !== base.context_hash
      || g.source.binding_id !== base.context.binding_id || g.source.delivery_hash !== base.context.delivery_hash
      || g.entity_id !== g.source.source_entity.id || conditions.some(c => c.source_entity_id !== g.entity_id)
      || !g.source.members.some(m => m.position_binding?.opportunity_unit_id === base.plan.target.unit_id && m.position_binding.opportunity_unit_version_id === base.plan.target.unit_version_id)
      || !Array.isArray(originals) || conditions.length !== originals.length
      || stable(conditions) !== stable(s.group_conditions.map(r => r.condition))) throw new Error("Invalid projection");
    if (g.rule_preview) {
      const rows = g.rule_preview.result.fact_review.result.rows;
      if (rows.length !== originals.length || g.rule_preview.result.rows.length !== rows.length) throw new Error("Invalid facts denominator");
      for (const [i, row] of rows.entries()) {
        const raw = originals[i], original = row.original;
        if (row.source_index !== conditions[i].source_index || row.entity_id !== g.entity_id
          || row.original_field !== raw.field || row.raw_value !== raw.value || row.original_status !== raw.status
          || original.field !== raw.field || original.value !== raw.value || original.status !== raw.status
          || (Object.hasOwn(original, "note") && (original.note ?? null) !== (raw.note ?? null))
          || stable(row.evidence.map(e => e.reference)) !== stable(original.evidence)
          || stable(row.evidence.map(e => ({ artifact_id: e.reference.artifact_id, quote: e.reference.quote, locator: e.reference.locator ?? {} }))) !== stable((raw.evidence ?? []).map(e => ({ artifact_id: e.artifact_id, quote: e.quote, locator: e.locator ?? {} })))) throw new Error("Fact differs from original");
      }
    }
    for (const row of s.group_conditions) {
      let reason = "GROUP_SOURCE_NOT_REGISTERED", disposition = "UNRESOLVED";
      let rule = null, approval = null, latest = null;
      if (g.registration) {
        reason = "GROUP_FACTS_NOT_PREPARED";
        if (g.rule_preview) {
          const source = g.rule_preview.result.rows.find(r => r.source_index === row.condition.source_index);
          if (!source) throw new Error("Missing source row");
          reason = source.reason_code;
          if (source.proposed_rule_payload) {
            reason = "GROUP_RULE_REVIEW_NOT_PREPARED";
            if (g.rule_review) {
              rule = g.rule_review.result.rows.find(r => r.source_index === row.condition.source_index) ?? null;
              if (!rule?.rule_candidate_id) throw new Error("Missing rule");
              approval = g.rule_review.decisions[rule.rule_candidate_id] ?? null;
              reason = approval ? `GROUP_RULE_${approval.decision}` : "GROUP_RULE_NOT_REVIEWED";
              if (approval?.decision === "APPROVE") {
                const history = g.applicability_histories[rule.rule_candidate_id];
                if (!Array.isArray(history)) throw new Error("Missing history");
                latest = history.at(-1) ?? null;
                reason = latest ? `GROUP_APPLICABILITY_${latest.request.outcome}` : "GROUP_APPLICABILITY_NOT_REVIEWED";
                disposition = latest?.request.outcome === "APPLIES" ? "INHERIT" : latest?.request.outcome === "DOES_NOT_APPLY" ? "EXCLUDE" : "UNRESOLVED";
                for (const [i, decision] of history.entries()) {
                  if (decision.sequence !== i + 1 || decision.request.previous_decision_id !== (history[i - 1]?.decision_id ?? null)
                    || decision.context.target_plan_id !== plan || decision.context.task_id !== task
                    || decision.context.source_rule_candidate_id !== rule.rule_candidate_id
                    || hash(decision.request) !== decision.request_hash || hash(decision.context) !== decision.context_hash
                    || hash(decision.evidence_snapshot) !== decision.evidence_hash) throw new Error("Invalid history");
                }
              }
            }
          }
        }
      }
      if (row.reason !== reason || row.disposition !== disposition || stable(row.source_rule) !== stable(rule)
        || stable(row.approval) !== stable(approval) || stable(row.applicability) !== stable(latest)) throw new Error("Invalid disposition");
    }
    return { ok: true, value: v };
  } catch (error) {
    const status = error instanceof LocalHumanTestApiError ? error.status : 0;
    return { ok: false, kind: [401, 403].includes(status) ? "forbidden" : [404, 409].includes(status) ? "stale" : "unavailable",
      error: "未取得有效的当前组条件预览，旧内容已隐藏。请核对权限或重新读取。" };
  }
}
