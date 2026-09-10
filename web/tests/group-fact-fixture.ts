import { createHash } from "node:crypto";
import type { GroupFactData, GroupFactRecord } from "../lib/group-facts";
import type { GroupSourceData, GroupSourceRecord } from "../lib/group-sources";
export function fixtureHash(value: unknown) { return createHash("sha256").update(JSON.stringify(value, (_key, item: unknown) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item)).digest("hex"); }
export function groupFactFixture(source: GroupSourceData, group: GroupSourceRecord): GroupFactData {
  source.preview.registration = group;
  source.preview.existing_group_id = group.group_identity.unit_id;
  const task = source.task, row = structuredClone(task.fact_review!.current!.rows[0]);
  row.entity_id = "unit-1"; row.original.entity_id = "unit-1"; row.source_index = 0;
  row.evidence[0].check_reference.entity_id = "unit-1";
  const known = { ...row, original_status: row.original.status, mapping_version: "group-fact-bridge/1.0.0" as const, target_scope: "UNIT" as const, ready_for_persistence: true, candidate_reason_code: "MAPPED", confidence: null };
  const unknown = structuredClone(known);
  unknown.source_index = 1; unknown.original_field = "户籍条件"; unknown.field_name = "household_registration";
  unknown.original = { ...unknown.original, field: unknown.original_field, value: null, status: "UNKNOWN" };
  unknown.raw_value = null; unknown.original_status = "UNKNOWN"; unknown.abstained = true; unknown.normalized_value_candidate = null;
  unknown.candidate_id = "019d0000-0000-7000-8000-000000004002";
  unknown.evidence[0].check_reference.fact_index = 1; unknown.evidence[0].check_reference.field = unknown.original_field;
  const unresolved = structuredClone(unknown);
  unresolved.source_index = 2; unresolved.original_field = "Word 补充条件"; unresolved.original.field = unresolved.original_field;
  unresolved.candidate_id = null; unresolved.ready_for_persistence = false; unresolved.issue_codes = ["UNKNOWN_EVIDENCE_UNVERIFIED"];
  unresolved.evidence[0].binding = null; Object.assign(unresolved.evidence[0].check_reference, { fact_index: 2, field: unresolved.original_field, verdict: "UNVERIFIED", persistent_binding: null });
  const peer = structuredClone(task.facts[0]);
  task.facts = [known.original, unknown.original, unresolved.original, peer];
  task.evidence_check!.references = [known, unknown, unresolved].map(row => row.evidence[0].check_reference);
  const result: GroupFactRecord["result"] = { contract_version: "group-fact-bridge/1.0.0", scope: "GROUP_FACT_REVIEW_ONLY", group_source: group,
    check_id: task.evidence_check!.check_id, check_hash: task.evidence_check!.result_hash, source_row_count: 4, rows: [known, unknown, unresolved],
    excluded_rows: [{ source_index: 3, entity_id: peer.entity_id, source_hash: fixtureHash(peer), reason: "DIFFERENT_ENTITY_SCOPE" }], extraction_run_id: "019d0000-0000-7000-8000-000000004003" };
  return { source, record: { preparation_id: "019d0000-0000-7000-8000-000000004001", result, result_hash: fixtureHash(result), reviewer_id: group.reviewer_id, created_at: task.updated_at, decisions: {}, history: [], fact_set: null } };
}
