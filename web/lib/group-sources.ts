import type { InvestigationTask } from "./investigations";

export const groupContract = "group-identity/1.0.0";
export const groupScope = "GROUP_SOURCE_ASSOCIATION_ONLY";
export interface GroupSourceIdentity { task_id: string; entity_id: string }
type PositionBinding = NonNullable<InvestigationTask["entity_binding"]>["positions"][number];
export interface GroupSource {
  contract_version: typeof groupContract; scope: typeof groupScope;
  task_id: string; delivery_hash: string; binding_id: string; binding_hash: string;
  opportunity_id: string; opportunity_version: number; source_bundle_revision_id: string;
  canonical_bundle_hash: string; source_snapshot_hash: string;
  source_group: { id: string; name?: string; positions: { id: string; name?: string; code?: string; [key: string]: unknown }[]; [key: string]: unknown };
  source_entity: { id: string; kind: "unit"; [key: string]: unknown };
  members: { entity_id: string; state: "BOUND" | "UNPROCESSED"; position_binding: PositionBinding | null }[];
  membership_status: "NO_MEMBERS" | "UNPROCESSED_MEMBERS" | "ALL_MEMBERS_BOUND";
}
export interface GroupSourceRecord {
  contract_version: typeof groupContract; scope: typeof groupScope; group_binding_id: string;
  group_identity: { unit_kind: "GROUP"; unit_id: string; public_id: string; unit_version_id: string; version: number; key: string; label: string };
  source: GroupSource; source_hash: string; reviewer_id: string; created_at: string;
}
export interface GroupSourcePreview { source: GroupSource; source_hash: string; existing_group_id: string | null; registration: GroupSourceRecord | null }
export interface GroupSourceData { task: InvestigationTask; preview: GroupSourcePreview }
export type GroupSourceResult = { ok: true; value: GroupSourceData } | { ok: false; kind: "invalid" | "stale" | "forbidden" | "unavailable"; error: string };
export function groupPreviewPath(identity: GroupSourceIdentity) {
  return `/review/investigations/${encodeURIComponent(identity.task_id)}/group-source?entity_id=${encodeURIComponent(identity.entity_id)}`;
}
export function groupRecordPath(taskId: string, recordId: string) {
  return `/review/investigations/${encodeURIComponent(taskId)}/group-bindings/${encodeURIComponent(recordId)}`;
}
