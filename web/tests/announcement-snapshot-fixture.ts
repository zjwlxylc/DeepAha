// Synthetic source relationships for engineering tests, not actual human approval.
import type { unitSnapshotFixture } from "./investigations-fixture";
import type { AnnouncementSnapshotData, AnnouncementSnapshotInput, AnnouncementSnapshotRecord } from "../lib/announcement-snapshots";

export const announcementSnapshotId = "019d0000-0000-7000-8000-000000002001";
export function announcementSnapshotFixture(data: ReturnType<typeof unitSnapshotFixture>): AnnouncementSnapshotData {
  const { task, snapshot: base } = data;
  const source = task.rule_review!.current[0].source_rows[0];
  const condition = structuredClone(base.plan.manifest.conditions[0]);
  const dispositions = ["INHERITED", "EXCLUDED", "UNRESOLVED"] as const;
  const rows = dispositions.map((disposition, index) => {
    const sourceIndex = task.rule_review!.current[0].source_rows.length;
    const id = `019d0000-0000-7000-8000-${String(2100 + index).padStart(12, "0")}`;
    const parent = structuredClone(source);
    parent.source_index = sourceIndex; parent.entity_id = "announcement"; parent.candidate_id = id;
    parent.original_field = ["公告学历条件", "公告专业条件", "公告例外条件"][index];
    parent.original = { ...parent.original, entity_id: "announcement", field: parent.original_field, value: "公告要求保留原始文字", note: index === 2 ? "Word 补充说明尚未核验" : null };
    task.rule_review!.current[0].source_rows.push(parent);
    const original = { ...condition, condition_id: `source:${sourceIndex}`, scope: "ANNOUNCEMENT" as const, source_index: sourceIndex, source_entity_id: "announcement", fact_id: null, state: "UNPROCESSED", source_unit_id: null, source_unit_version: null, source_unit_version_id: null };
    base.plan.manifest.conditions.push(original);
    base.plan.dispositions.push({ condition_id: original.condition_id, kind: "UNRESOLVED", rule_ids: [], decision_id: null, reason: "CONDITION_REVIEW_REQUIRED" });
    base.context.source_row_count += 1;
    const approval = { decision_id: id, rule_candidate_id: id, rule_preparation_id: id, reviewer_id: "synthetic-reviewer", request_hash: "d".repeat(64), request: { reason: "合成独立规则审核", decision: "APPROVE" }, approval: { approver_identity: "human:synthetic-reviewer", decided_at: "2026-09-09T00:00:00Z" } };
    const evidence = source.evidence[0].binding!;
    const outcome = disposition === "INHERITED" ? "APPLIES" as const : "DOES_NOT_APPLY" as const;
    const context = { target_plan_id: base.plan_id, source_rule_preparation_id: id, source_rule_candidate_id: id, source_rule_approval_id: id, target: base.plan.target };
    return { condition: original, source_fact: index === 2 ? null : { verified_fact_id: id, verified_fact_set_id: id, candidate_id: id, field_name: "education_level", fact_state: "KNOWN", normalized_value: "MASTER", raw_value: "硕士", verification: { decision: "APPROVE", verifier_identity: "human:synthetic-reviewer" } },
      source_rule: index === 2 ? null : { rule_id: id, field: "education_level", operator: "GTE", value: "MASTER" }, source_rule_approval: index === 2 ? null : approval,
      applicability: index === 2 ? null : { decision_id: id, sequence: 1, request_hash: "d".repeat(64), context, context_hash: "e".repeat(64),
        request: { target_plan_id: base.plan_id, source_rule_preparation_id: id, source_rule_candidate_id: id, context_hash: "e".repeat(64), previous_decision_id: null, outcome, reason: "合成适用性审阅，不是真人批准", evidence: [{ member_id: id, block_id: evidence.block_id, quote: "  保留公告适用范围原文。\n" }] },
        evidence_snapshot: [{ member_id: id, block_id: evidence.block_id, quote: "  保留公告适用范围原文。\n", material_id: source.original.evidence[0].artifact_id, source_url: `https://example.test/announcement/${index}`, document_id: task.rule_review!.current[0].rows[0].evidence[0].document_id, evidence_ref_id: evidence.evidence_ref_id, block_hash: "c".repeat(64), binding_hash: "d".repeat(64), locator: evidence.structural_locator }],
        evidence_hash: "f".repeat(64), reviewer_id: "synthetic-reviewer", created_at: "2026-09-09T00:00:00Z" },
      disposition, reasons: index === 2 ? ["SOURCE_EVIDENCE_UNVERIFIED", "APPLICABILITY_NOT_REVIEWED"] : [] };
  });
  const input: AnnouncementSnapshotInput = { dependencies: { contract_version: "investigation-announcement-snapshot/1.0.0", adapter_version: "investigation-announcement-adapter/1.0.0", base_plan_id: base.plan_id, base_plan_hash: base.plan_hash, base_context_hash: base.context_hash, fact_preparation_id: base.plan.manifest.preparation_id, fact_preparation_hash: base.plan.manifest.preparation_sha256 }, dependencies_hash: "f".repeat(64), snapshot: { scope: "DERIVED_SCOPE_SNAPSHOT_ONLY", contract_version: "investigation-announcement-snapshot/1.0.0", adapter_version: "investigation-announcement-adapter/1.0.0", base_v2: base, announcement_conditions: rows, overall_qualification: "UNCERTAIN" } };
  return { task, input, record: null };
}
export function announcementRecordFixture(input: AnnouncementSnapshotInput): AnnouncementSnapshotRecord {
  return { ...structuredClone(input), snapshot_id: announcementSnapshotId, base_plan_id: input.snapshot.base_v2.plan_id, contract_version: input.snapshot.contract_version, adapter_version: input.snapshot.adapter_version, snapshot_hash: "a".repeat(64), reviewer_id: "synthetic-reviewer", created_at: "2026-09-09T00:00:00Z" };
}
