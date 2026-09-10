import type { GroupSource, GroupSourceRecord } from "./group-sources";
import type { GroupRulePreview } from "./group-rules";
import type { GroupRuleDecision, GroupRuleReviewRecord } from "./group-rule-review";
import type { GroupApplicabilityDecision } from "./group-applicability-decisions";
import type { InvestigationUnitSnapshot } from "./unit-snapshots";
import type { ApplicabilityResult } from "./rule-applicability";

export const inheritanceVersion = "group-inheritance-preview/1.0.0";
export interface GroupInheritance {
  dependencies: {
    contract_version: typeof inheritanceVersion; base_v2: InvestigationUnitSnapshot;
    group_source: { entity_id: string; source: GroupSource; registration: GroupSourceRecord | null;
      rule_preview: GroupRulePreview | null; rule_review: GroupRuleReviewRecord | null;
      applicability_histories: Record<string, GroupApplicabilityDecision[]> };
  };
  dependencies_hash: string;
  snapshot: { contract_version: typeof inheritanceVersion; scope: "GROUP_INHERITANCE_PREVIEW_ONLY";
    base_v2: InvestigationUnitSnapshot; overall_qualification: "UNCERTAIN";
    group_conditions: { condition: InvestigationUnitSnapshot["plan"]["manifest"]["conditions"][number];
      disposition: "INHERIT" | "EXCLUDE" | "UNRESOLVED"; reason: string;
      source_rule: GroupRuleReviewRecord["result"]["rows"][number] | null;
      approval: GroupRuleDecision | null; applicability: GroupApplicabilityDecision | null }[];
  };
  snapshot_hash: string;
}
export type GroupInheritanceResult = ApplicabilityResult<GroupInheritance>;
export function groupInheritancePath(task: string, plan: string) {
  return `/review/investigations/${encodeURIComponent(task)}/unit-plans/${encodeURIComponent(plan)}/group-inheritance`;
}
export const inheritanceReasons: Record<string, string> = {
  GROUP_SOURCE_NOT_REGISTERED: "组来源尚未登记", GROUP_FACTS_NOT_PREPARED: "组事实尚未准备",
  FACT_SET_NOT_SAVED: "正式事实集尚未保存", FACT_UNKNOWN: "调查后信息不足",
  FACT_REJECTED: "事实候选被拒绝；不代表条件不适用", GROUP_FIELD_UNPROCESSED: "字段尚未处理",
  FIELD_NOT_EXECUTABLE: "此字段尚不能形成可执行规则", GROUP_RULE_REVIEW_NOT_PREPARED: "独立规则审核尚未准备",
  GROUP_RULE_NOT_REVIEWED: "规则尚未审核", GROUP_RULE_REJECT: "规则被拒绝；仍待处理",
  GROUP_RULE_NEEDS_ADJUDICATION: "规则需要裁决", GROUP_APPLICABILITY_NOT_REVIEWED: "岗位适用范围尚未审核",
  GROUP_APPLICABILITY_APPLIES: "已明确适用于本岗位，仅作范围预览",
  GROUP_APPLICABILITY_DOES_NOT_APPLY: "已明确不适用于本岗位",
  GROUP_APPLICABILITY_NEEDS_ADJUDICATION: "岗位适用范围需要裁决",
};
