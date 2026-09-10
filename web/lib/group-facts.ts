import type { GroupSourceData, GroupSourceRecord } from "./group-sources";
import type { InvestigationFactPreparation } from "./investigations";

export const groupFactContract = "group-fact-bridge/1.0.0";
export type GroupDecision = "APPROVE" | "REJECT" | "UNKNOWN" | "NEEDS_ADJUDICATION";
export type GroupFactRow = InvestigationFactPreparation["rows"][number] & {
  original_status: string; mapping_version: typeof groupFactContract; target_scope: "UNIT";
  ready_for_persistence: boolean; candidate_reason_code: string; confidence: null;
}
export interface GroupFactDecision { candidate_id: string; decision_id: string; decision: GroupDecision; reason: string; reviewer_id: string; created_at: string }
export interface GroupFactRecord {
  preparation_id: string; result_hash: string; reviewer_id: string; created_at: string;
  result: { contract_version: typeof groupFactContract; scope: "GROUP_FACT_REVIEW_ONLY"; group_source: GroupSourceRecord;
    check_id: string; check_hash: string; source_row_count: number; rows: GroupFactRow[];
    excluded_rows: { source_index: number; entity_id: string; source_hash: string; reason: "DIFFERENT_ENTITY_SCOPE" }[];
    extraction_run_id: string | null };
  decisions: Record<string, GroupFactDecision>; history: GroupFactDecision[];
  fact_set: { fact_set_id: string; status: string; version: number; reason: string } | null;
}
export interface GroupFactData { source: GroupSourceData; record: GroupFactRecord | null }
export type GroupFactResult = { ok: true; value: GroupFactData } | { ok: false; kind: "invalid" | "stale" | "forbidden" | "unavailable"; error: string };
export type GroupFactCommand = { kind: "prepare"; group_binding_id: string; check_id: string; expected_source_hash: string }
  | { kind: "decision"; preparation_id: string; expected_preparation_hash: string; candidate_id: string; decision: GroupDecision; evidence_support: "SUPPORTED" | "UNSUPPORTED" | "UNKNOWN"; precedence_check: "PASSED" | "FAILED" | "UNKNOWN"; reason: string }
  | { kind: "promote"; preparation_id: string; expected_preparation_hash: string; reason: string };
export function groupFactStartPath(taskId: string, groupId: string) { return `/review/investigations/${encodeURIComponent(taskId)}/group-bindings/${encodeURIComponent(groupId)}/facts`; }
export function groupFactRecordPath(taskId: string, prepId: string) { return `/review/investigations/${encodeURIComponent(taskId)}/group-facts/${encodeURIComponent(prepId)}`; }
