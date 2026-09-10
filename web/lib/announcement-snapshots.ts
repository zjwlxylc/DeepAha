import type { InvestigationTask } from "./investigations";
import type { ApplicabilityDecision, ApplicabilityView } from "./rule-applicability";
import type { InvestigationUnitSnapshot } from "./unit-snapshots";

export const announcementSnapshotContract = "investigation-announcement-snapshot/1.0.0";
export const announcementSnapshotAdapter = "investigation-announcement-adapter/1.0.0";
export interface AnnouncementSnapshotIdentity { task_id: string; base_plan_id: string }
export interface AnnouncementCondition {
  condition: InvestigationUnitSnapshot["plan"]["manifest"]["conditions"][number];
  source_fact: { verified_fact_id: string; verified_fact_set_id: string; candidate_id: string; field_name: string; fact_state: string; normalized_value: unknown; raw_value: unknown; verification: Record<string, unknown>; [key: string]: unknown } | null;
  source_rule: ApplicabilityView["source_rule"] | null;
  source_rule_approval: { decision_id: string; rule_candidate_id: string; rule_preparation_id: string; reviewer_id: string; request_hash: string; request: { reason: string; decision: string; [key: string]: unknown }; approval: { approver_identity: string; decided_at: string; [key: string]: unknown }; [key: string]: unknown } | null;
  applicability: ApplicabilityDecision | null;
  disposition: "INHERITED" | "EXCLUDED" | "UNRESOLVED";
  reasons: string[];
}
export interface AnnouncementSnapshotInput {
  dependencies: { contract_version: string; adapter_version: string; base_plan_id: string; base_plan_hash: string; base_context_hash: string; fact_preparation_id: string; fact_preparation_hash: string; [key: string]: unknown };
  dependencies_hash: string;
  snapshot: { scope: "DERIVED_SCOPE_SNAPSHOT_ONLY"; contract_version: string; adapter_version: string; base_v2: InvestigationUnitSnapshot; announcement_conditions: AnnouncementCondition[]; overall_qualification: "UNCERTAIN" };
}
export interface AnnouncementSnapshotRecord extends AnnouncementSnapshotInput {
  snapshot_id: string; base_plan_id: string; contract_version: string; adapter_version: string;
  snapshot_hash: string; reviewer_id: string; created_at: string;
}
export interface AnnouncementSnapshotData { task: InvestigationTask; input: AnnouncementSnapshotInput; record: AnnouncementSnapshotRecord | null }
export type AnnouncementSnapshotResult = { ok: true; value: AnnouncementSnapshotData } | { ok: false; kind: "invalid" | "stale" | "forbidden" | "unavailable"; error: string };
export function announcementPreviewPath(identity: AnnouncementSnapshotIdentity) {
  return `/review/investigations/${encodeURIComponent(identity.task_id)}/unit-plans/${encodeURIComponent(identity.base_plan_id)}/announcement-snapshot`;
}
export function announcementRecordPath(taskId: string, snapshotId: string) {
  return `/review/investigations/${encodeURIComponent(taskId)}/announcement-snapshots/${encodeURIComponent(snapshotId)}`;
}
export const announcementReasons: Record<string, string> = {
  SOURCE_FACT_REJECTED: "公告字段已拒绝，不能据此继承",
  SOURCE_FACT_NOT_PROMOTED: "公告字段尚未保存为审核事实",
  SOURCE_FACT_CANDIDATE_MISSING: "尚无可审核的公告字段候选",
  SOURCE_FACT_UNKNOWN: "已保存公告事实仍为未知",
  SOURCE_EVIDENCE_UNVERIFIED: "公告证据尚未完成核验",
  SOURCE_FIELD_UNSUPPORTED: "当前不支持处理该公告字段",
  SOURCE_CONDITION_CONFLICT: "公告条件存在冲突",
  SOURCE_CONDITION_UNKNOWN: "公告条件信息不足",
  SOURCE_CONDITION_UNPROCESSED: "公告条件尚未完成处理",
  SOURCE_RULE_PREPARATION_MISSING: "尚未整理公告规则",
  SOURCE_RULE_CANDIDATE_MISSING: "尚无可用的公告规则候选",
  SOURCE_RULE_REJECTED: "公告规则已拒绝",
  SOURCE_RULE_APPROVAL_REQUIRED: "公告规则尚未独立批准",
  SOURCE_RULE_GROUP_UNRESOLVED: "本公告仍有规则尚未终局裁决",
  APPLICABILITY_NOT_REVIEWED: "尚无对本岗位的适用性决定",
  APPLICABILITY_NEEDS_ADJUDICATION: "对本岗位的适用性仍待裁决",
};
