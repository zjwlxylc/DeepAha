import type { InvestigationTask } from "./investigations";
import type { InvestigationUnitSnapshot } from "./unit-snapshots";

export const applicabilityOutcomes = {
  APPLIES: "适用于此岗位",
  DOES_NOT_APPLY: "不适用于此岗位",
  NEEDS_ADJUDICATION: "待裁决",
} as const;
export type ApplicabilityOutcome = keyof typeof applicabilityOutcomes;
export interface ApplicabilityIdentity {
  task_id: string;
  target_plan_id: string;
  source_rule_preparation_id: string;
  source_rule_candidate_id: string;
}
export interface ApplicabilityEvidence {
  member_id: string; block_id: string; material_id: string; document_id: string;
  evidence_ref_id: string; source_url: string; text: string; locator: Record<string, unknown>;
}
export interface ApplicabilitySelection { member_id: string; block_id: string; quote: string }
export interface ApplicabilityRequest {
  target_plan_id: string; source_rule_preparation_id: string; source_rule_candidate_id: string;
  context_hash: string; previous_decision_id: string | null; outcome: ApplicabilityOutcome;
  evidence: ApplicabilitySelection[]; reason: string;
}
export interface ApplicabilityContext {
  target_plan_id: string; source_rule_preparation_id: string; source_rule_candidate_id: string;
  target: InvestigationUnitSnapshot["plan"]["target"];
  [key: string]: unknown;
}
export interface ApplicabilityDecision {
  decision_id: string; sequence: number; request: ApplicabilityRequest; request_hash: string;
  context: ApplicabilityContext; context_hash: string;
  evidence_snapshot: (ApplicabilitySelection & Omit<ApplicabilityEvidence, "text"> & { block_hash: string; binding_hash: string })[];
  evidence_hash: string; reviewer_id: string; created_at: string;
}
export interface ApplicabilityView {
  scope: "RULE_APPLICABILITY_REVIEW_ONLY";
  context: ApplicabilityContext; context_hash: string; target_label: string; source_label: string;
  source_rule: { rule_id: string; field: string | null; operator: string; value: unknown; reason_template?: string };
  latest: ApplicabilityDecision | null; history: ApplicabilityDecision[];
  evidence_options: ApplicabilityEvidence[]; next_cursor: string | null;
}
export type ApplicabilityResult<T> = { ok: true; value: T } | {
  ok: false; kind: "invalid" | "unavailable" | "stale" | "forbidden"; error: string;
};

export function applicabilityPath(identity: ApplicabilityIdentity) {
  return `/investigations/${encodeURIComponent(identity.task_id)}/unit-plans/${encodeURIComponent(identity.target_plan_id)}/rule-applicability/${encodeURIComponent(identity.source_rule_preparation_id)}/${encodeURIComponent(identity.source_rule_candidate_id)}`;
}

export function matchesApplicabilityIdentity(view: ApplicabilityView, identity: ApplicabilityIdentity) {
  return view.scope === "RULE_APPLICABILITY_REVIEW_ONLY"
    && view.context.target_plan_id === identity.target_plan_id
    && view.context.source_rule_preparation_id === identity.source_rule_preparation_id
    && view.context.source_rule_candidate_id === identity.source_rule_candidate_id;
}

export function currentAnnouncementRules(task: InvestigationTask, snapshot: InvestigationUnitSnapshot) {
  const facts = task.fact_review?.current, ctx = snapshot.context, target = snapshot.plan.target;
  if (!facts) return [];
  return (task.rule_review?.current ?? []).filter(prep =>
    prep.target.target_scope === "OPPORTUNITY" && prep.target.entity_kind === "announcement"
    && prep.target.opportunity_id === target.opportunity_id
    && prep.target.opportunity_version === target.opportunity_version
    && prep.binding_id === ctx.binding_id && prep.check_id === ctx.check_id
    && prep.delivery_hash === ctx.delivery_hash && prep.fact_preparation_id === facts.preparation_id
    && prep.fact_preparation_hash === facts.result_hash && prep.source_bundle_revision_id === ctx.source_bundle_revision_id
    && prep.fact_set_id === facts.active_fact_sets[prep.entity_id]?.fact_set_id
    && prep.rows.every(row => !row.rule_candidate_id || ["APPROVE", "REJECT"].includes(prep.decisions[row.rule_candidate_id]?.decision)),
  ).flatMap(prep => prep.rows.filter(row => row.rule_candidate_id && row.payload
    && prep.decisions[row.rule_candidate_id]?.decision === "APPROVE").map(row => ({ prep, row })));
}
