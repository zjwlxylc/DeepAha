import type { GroupSourceData, GroupSourceRecord } from "../lib/group-sources";
import type { InvestigationTask } from "../lib/investigations";

export const groupRecordId = "019d0000-0000-7000-8000-000000003001";
export function groupSourceFixture(task: InvestigationTask): GroupSourceData {
  const binding = task.entity_binding!, target = task.fact_review!.current!.targets[0];
  const group = { id: "unit-1", name: "示例学院（合成）", parent_id: null, positions: [
    { id: "position-1", name: "教学岗位", code: "P001" }, { id: "position-2", name: "尚未关联的研究岗位", code: "P002" },
  ], note: "组条件及 Word 补充说明仍需单独核验。" };
  task.opportunities = { ...task.opportunities, units: [group] };
  task.binding_entities = [{ id: group.id, name: group.name, kind: "unit" }, ...group.positions.map(p => ({ ...p, kind: "position" }))];
  binding.positions = [{ entity_id: "position-1", opportunity_unit_id: target.opportunity_unit_id!, opportunity_unit_version_id: target.opportunity_unit_version_id! }];
  binding.unmapped_position_ids = ["position-2"];
  return { task, preview: { source_hash: "c".repeat(64), existing_group_id: null, registration: null, source: {
    contract_version: "group-identity/1.0.0", scope: "GROUP_SOURCE_ASSOCIATION_ONLY", task_id: task.task_id,
    delivery_hash: task.delivery_hash!, binding_id: binding.binding_id, binding_hash: "b".repeat(64),
    opportunity_id: binding.opportunity_id, opportunity_version: binding.opportunity_version,
    source_bundle_revision_id: binding.source_bundle_revision_id, canonical_bundle_hash: binding.canonical_bundle_hash, source_snapshot_hash: "d".repeat(64),
    source_group: group, source_entity: { id: group.id, kind: "unit", parent_id: "announcement-1", name: group.name },
    members: [{ entity_id: "position-1", state: "BOUND", position_binding: binding.positions[0] }, { entity_id: "position-2", state: "UNPROCESSED", position_binding: null }],
    membership_status: "UNPROCESSED_MEMBERS",
  } } };
}
export function groupRecordFixture(data: GroupSourceData): GroupSourceRecord {
  return { contract_version: "group-identity/1.0.0", scope: "GROUP_SOURCE_ASSOCIATION_ONLY", group_binding_id: groupRecordId,
    source: structuredClone(data.preview.source), source_hash: data.preview.source_hash,
    group_identity: { unit_kind: "GROUP", unit_id: "019d0000-0000-7000-8000-000000003002", public_id: "unit_019d0000000070008000000000003002", unit_version_id: "019d0000-0000-7000-8000-000000003003", version: 1, key: "group:synthetic", label: "示例学院（合成）" },
    reviewer_id: "019d0000-0000-7000-8000-000000003004", created_at: data.task.updated_at };
}
