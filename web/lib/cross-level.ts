import type { GroupInheritance } from "./group-inheritance";
import type { AnnouncementSnapshotInput } from "./announcement-snapshots";
import type { ApplicabilityResult } from "./rule-applicability";

export const crossLevelVersion = "cross-level-condition-review/1.0.0";
type Condition = GroupInheritance["snapshot"]["group_conditions"][number]["condition"];
export interface RawCondition {
  field: string; value: unknown; note?: string | null;
  evidence?: { artifact_id: string; quote: string; locator?: unknown }[];
}
export interface CrossLevelReview {
  dependencies: { contract_version: typeof crossLevelVersion; group: GroupInheritance;
    announcement: AnnouncementSnapshotInput & { dependencies: AnnouncementSnapshotInput["dependencies"] & {
      announcement_sources: { entity_id: string; source_rows: { source_index: number; original: RawCondition }[] }[];
    } } };
  dependencies_hash: string;
  snapshot: { contract_version: typeof crossLevelVersion; scope: "CROSS_LEVEL_REVIEW_ONLY";
    target: GroupInheritance["snapshot"]["base_v2"]["plan"]["target"]; base_v2_hash: string;
    conditions: { condition: Condition; disposition: "LOCAL" | "INHERITED" | "EXCLUDED" | "UNRESOLVED"; source_pointer: string }[];
    semantic_review_groups: { field_name: string; condition_ids: string[]; excluded_condition_ids: string[]; relation: "NOT_EVALUATED" }[];
    blockers: string[]; executable: false; overall_qualification: "UNCERTAIN";
  };
  snapshot_hash: string;
}
export type CrossLevelResult = ApplicabilityResult<CrossLevelReview>;
export function crossLevelPath(task: string, plan: string) {
  return `/review/investigations/${encodeURIComponent(task)}/unit-plans/${encodeURIComponent(plan)}/cross-level`;
}
export function originalCondition(value: CrossLevelReview, condition: Condition): RawCondition | undefined {
  if (condition.scope === "ANNOUNCEMENT") return value.dependencies.announcement.dependencies.announcement_sources
    .find(s => s.entity_id === condition.source_entity_id)?.source_rows.find(r => r.source_index === condition.source_index)?.original;
  const group = value.dependencies.group.dependencies.group_source;
  const peers = value.snapshot.conditions.filter(r => r.condition.scope === condition.scope && r.condition.source_entity_id === condition.source_entity_id);
  const index = peers.findIndex(r => r.condition.condition_id === condition.condition_id);
  const originals = condition.scope === "EMPLOYER_GROUP" ? group.source.source_group.unit_level
    : group.source.source_group.positions.find(p => p.id === condition.source_entity_id)?.facts;
  return Array.isArray(originals) ? originals[index] as RawCondition | undefined : undefined;
}
