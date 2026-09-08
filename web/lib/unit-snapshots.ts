import type { InvestigationEvidenceCheck, InvestigationTask } from "./investigations";

export interface InvestigationUnitSnapshot {
  plan_id: string; plan_hash: string; context_hash: string; reviewer_id: string; created_at: string;
  plan: {
    qualification_plan_id: string; contract_version: string;
    target: { opportunity_id: string; opportunity_version: number; unit_id: string; unit_version: number; unit_version_id: string };
    manifest: { preparation_id: string; preparation_sha256: string; upstream_blockers: string[]; conditions: {
      condition_id: string; source_entity_id: string; source_index: number; field_name: string;
      scope: "UNIT" | "ANNOUNCEMENT" | "EMPLOYER_GROUP"; state: string; source_sha256: string;
      fact_id: string | null; evidence_ref_ids: string[];
    }[] };
    dispositions: { condition_id: string; kind: string; rule_ids: string[]; decision_id: string | null; reason: string }[];
    rules: { rule_id: string; field: string | null; operator: string; value: unknown }[];
    admissions: { rule_id: string; approval_decision_id: string; producer_principal_id: string; reviewer_principal_id: string; reviewed_at: string; evidence_validity: { evidence_ref_id: string; valid_from: string; valid_until: string | null }[] }[];
  };
  context: {
    adapter_version: string; rule_preparation_id: string; rule_preparation_hash: string;
    fact_preparation_hash: string; binding_id: string; check_id: string; delivery_hash: string;
    fact_set_id: string; fact_set_version: number; source_bundle_revision_id: string;
    source_row_count: number; excluded_source_rows: { source_index: number; entity_id: string; source_sha256: string; reason: string }[];
    source_notes: { condition_id: string; note: string }[];
    evidence_reference_counts: Record<"PASS" | "FAIL" | "UNVERIFIED", number>;
    unresolved_source_references: InvestigationEvidenceCheck["references"];
  };
}

export function currentSnapshotSource(snapshot: InvestigationUnitSnapshot, task: InvestigationTask) {
  const ctx = snapshot.context, facts = task.fact_review?.current;
  const prep = task.rule_review?.current.find(p => p.rule_preparation_id === ctx.rule_preparation_id);
  return task.status === "APPROVED" && prep && facts
    && task.delivery_hash === ctx.delivery_hash && task.entity_binding?.binding_id === ctx.binding_id
    && task.evidence_check?.check_id === ctx.check_id && facts.preparation_id === snapshot.plan.manifest.preparation_id
    && facts.result_hash === ctx.fact_preparation_hash && prep.result_hash === ctx.rule_preparation_hash
    && facts.active_fact_sets[prep.entity_id]?.fact_set_id === ctx.fact_set_id
    && prep.target.opportunity_unit_version_id === snapshot.plan.target.unit_version_id
    ? prep : null;
}
