export const ruleDecisions = { APPROVE: "批准拟规则", REJECT: "拒绝拟规则", NEEDS_ADJUDICATION: "需要进一步裁决" } as const;
export const ruleAuthorities = {
  LATEST_OFFICIAL_CORRECTION: "最新官方更正", FORMAL_OFFICIAL_ATTACHMENT: "正式官方附件",
  ORIGINAL_OFFICIAL_NOTICE: "原始正式公告", OFFICIAL_FAQ_GUIDANCE: "官方 FAQ／指南",
  HUMAN_APPROVED_MAPPING: "人工批准映射", LLM_SEMANTIC_INFERENCE: "模型语义推断",
} as const;
export const ruleRelations = { SUPPORTS: "支持该拟规则", CONTRADICTS: "与该拟规则矛盾" } as const;
export const ruleApplicability = { UNRESOLVED: "尚未确认", APPLIES_TO_EXACT_TARGET: "已核对，适用于此精确目标" } as const;

export function isExplicitRuleTime(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second, zone] = match;
  const y = Number(year), m = Number(month), d = Number(day);
  const days = [31, y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return y >= 1 && m >= 1 && m <= 12 && d >= 1 && d <= days[m - 1]
    && Number(hour) <= 23 && Number(minute) <= 59 && Number(second ?? 0) <= 59
    && (zone === "Z" || (Number(zone.slice(1, 3)) <= 23 && Number(zone.slice(4)) <= 59));
}
