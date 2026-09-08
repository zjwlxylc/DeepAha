// Synthetic browser/component inputs only; not a human applicability decision.
import type { unitSnapshotFixture } from "./investigations-fixture";
import type { ApplicabilityDecision, ApplicabilityIdentity, ApplicabilityRequest, ApplicabilityView } from "../lib/rule-applicability";

export const applicabilityIds = {
  sourcePreparation: "019d0000-0000-7000-8000-000000001001",
  sourceCandidate: "019d0000-0000-7000-8000-000000001002",
  sourceFactSet: "019d0000-0000-7000-8000-000000001003",
  member: "019d0000-0000-7000-8000-000000001004",
  block: "019d0000-0000-7000-8000-000000001005",
  secondBlock: "019d0000-0000-7000-8000-000000001006",
  decision: "019d0000-0000-7000-8000-000000001007",
};

export function applicabilityTaskFixture(data: ReturnType<typeof unitSnapshotFixture>) {
  const target = data.task.rule_review!.current[0];
  const source = structuredClone(target);
  source.rule_preparation_id = applicabilityIds.sourcePreparation;
  source.fact_set_id = applicabilityIds.sourceFactSet;
  source.entity_id = "announcement";
  source.target = { ...source.target, entity_id: "announcement", entity_kind: "announcement", name: "示例招聘公告", target_scope: "OPPORTUNITY", opportunity_unit_id: null, opportunity_unit_version_id: null };
  source.result_hash = "e".repeat(64);
  source.rows[0].rule_candidate_id = applicabilityIds.sourceCandidate;
  source.decisions = { [applicabilityIds.sourceCandidate]: { ...Object.values(target.decisions)[0], rule_candidate_id: applicabilityIds.sourceCandidate, decision: "APPROVE" } };
  data.task.rule_review!.current.push(source);
  data.task.fact_review!.current!.active_fact_sets.announcement = { fact_set_id: source.fact_set_id, version: 1, source_bundle_revision_id: source.source_bundle_revision_id };
  return data;
}

export function applicabilityViewFixture(data: ReturnType<typeof unitSnapshotFixture>) {
  const { task, snapshot } = applicabilityTaskFixture(data);
  const identity: ApplicabilityIdentity = { task_id: task.task_id, target_plan_id: snapshot.plan_id, source_rule_preparation_id: applicabilityIds.sourcePreparation, source_rule_candidate_id: applicabilityIds.sourceCandidate };
  const view: ApplicabilityView = {
    scope: "RULE_APPLICABILITY_REVIEW_ONLY",
    context: { target_plan_id: identity.target_plan_id, source_rule_preparation_id: identity.source_rule_preparation_id, source_rule_candidate_id: identity.source_rule_candidate_id, target: snapshot.plan.target, binding_id: snapshot.context.binding_id },
    context_hash: "c".repeat(64), target_label: "教学岗位", source_label: "示例招聘公告",
    source_rule: { rule_id: identity.source_rule_candidate_id, field: "education_level", operator: "GTE", value: "MASTER" },
    latest: null, history: [],
    evidence_options: [{ member_id: applicabilityIds.member, block_id: applicabilityIds.block, document_id: task.rule_review!.current[0].rows[0].evidence[0].document_id, material_id: task.materials[0].artifact_id, source_url: "https://example.test/notices/announcement.html", evidence_ref_id: task.rule_review!.current[0].rows[0].evidence_ref_ids[0], text: "  公告所列学历条件适用于本公告全部岗位。\n  ", locator: { reader: "synthetic", block: 1 } }],
    next_cursor: `${applicabilityIds.block}:${applicabilityIds.member}`,
  };
  return { task, snapshot, identity, view };
}

export function applicabilityDecisionFixture(view: ApplicabilityView, changes: Partial<ApplicabilityRequest> = {}): ApplicabilityDecision {
  return {
    decision_id: applicabilityIds.decision, sequence: 1, request_hash: "d".repeat(64),
    request: { target_plan_id: view.context.target_plan_id, source_rule_preparation_id: view.context.source_rule_preparation_id, source_rule_candidate_id: view.context.source_rule_candidate_id,
      context_hash: view.context_hash, previous_decision_id: view.latest?.decision_id ?? null, outcome: "APPLIES", evidence: [{ member_id: view.evidence_options[0].member_id, block_id: view.evidence_options[0].block_id, quote: view.evidence_options[0].text }], reason: "合成审阅：公告明示适用于全部岗位。", ...changes },
    context: view.context, context_hash: view.context_hash, evidence_snapshot: [], evidence_hash: "e".repeat(64), reviewer_id: "synthetic-browser-reviewer", created_at: "2026-09-08T12:00:00Z",
  };
}
