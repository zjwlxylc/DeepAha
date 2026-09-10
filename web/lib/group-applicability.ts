import type { GroupRuleDecision, GroupRuleReviewRecord } from "./group-rule-review";
import type { GroupSourceRecord } from "./group-sources";
import type { InvestigationUnitSnapshot } from "./unit-snapshots";

export interface GroupApplicabilityIdentity {
  task_id: string; target_plan_id: string; source_rule_preparation_id: string; source_rule_candidate_id: string;
}
export interface GroupApplicabilityContext extends GroupApplicabilityIdentity {
  contract_version: "group-rule-applicability-context/1.0.0";
  target_plan_hash: string; target_plan_context_hash: string;
  target: InvestigationUnitSnapshot["plan"]["target"]; target_entity_id: string;
  source_group: GroupSourceRecord["group_identity"];
  group_binding_id: string; group_source_hash: string;
  member: GroupSourceRecord["source"]["members"][number];
  binding_id: string; check_id: string; source_bundle_revision_id: string;
  source_rule_preparation_hash: string; source_rule_approval_id: string;
  source_rule_approval_hash: string; source_review_hash: string;
}
export interface GroupApplicabilityView {
  scope: "GROUP_APPLICABILITY_CONTEXT_ONLY"; outcome: "UNDECIDED";
  context: GroupApplicabilityContext; context_hash: string;
  source_review: GroupRuleReviewRecord; target_plan: InvestigationUnitSnapshot;
  candidate: GroupRuleReviewRecord["result"]["rows"][number]; approval: GroupRuleDecision;
  evidence_options: { member_id: string; block_id: string; material_id: string; source_url: string; document_id: string; evidence_ref_id: string; text: string; locator: Record<string, unknown> }[];
  next_cursor: string | null;
}
export type GroupApplicabilityResult<T> = { ok: true; value: T } | { ok: false; kind?: "forbidden" | "stale" | "unavailable"; error: string };
export function groupApplicabilityPath(i: GroupApplicabilityIdentity) {
  return `/review/investigations/${encodeURIComponent(i.task_id)}/unit-plans/${encodeURIComponent(i.target_plan_id)}/group-applicability/${encodeURIComponent(i.source_rule_preparation_id)}/${encodeURIComponent(i.source_rule_candidate_id)}`;
}
