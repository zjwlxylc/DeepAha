import type { InvestigationTask } from "./investigations";

export function selectedPositions(task: InvestigationTask, ids: string[]) {
  return [...new Set(ids)].map(id => task.binding_entities?.find(e => e.id === id && e.kind === "position"))
    .filter((e): e is NonNullable<typeof e> => !!e).slice(0, 2);
}

export function reviewHref(taskId: string, ids: string[], entity?: string, stage = "facts", offset = 0, queue = "") {
  const q = new URLSearchParams();
  ids.forEach(id => q.append("position", id));
  if (entity) q.set("entity_id", entity);
  q.set("stage", stage);
  if (offset) q.set("offset", String(offset));
  if (queue) q.set("queue", queue);
  return `/review/investigations/${taskId}/check?${q}`;
}

export function factAnswer(support: string, scope: string, abstained: boolean) {
  if (!["yes", "no", "unsure"].includes(support) || (support === "yes" && !["clear", "uncertain"].includes(scope))) return null;
  if (support === "no") return { decision: "REJECT", evidence_support: "UNSUPPORTED", precedence_check: "UNKNOWN" };
  if (support === "unsure" || scope !== "clear") return { decision: "NEEDS_ADJUDICATION", evidence_support: support === "yes" ? "SUPPORTED" : "UNKNOWN", precedence_check: "UNKNOWN" };
  return { decision: abstained ? "UNKNOWN" : "APPROVE", evidence_support: "SUPPORTED", precedence_check: "PASSED" };
}

const words: Record<string, string> = {
  minimum_level: "最低学历", maximum_level: "最高学历", allowed_levels: "允许学历", major_codes: "专业代码",
  allowed_codes: "允许代码", allowed_regions: "允许地区", certificates: "所需证书", allowed_statuses: "允许身份",
  minimum_age: "最低年龄", maximum_age: "最高年龄", cutoff_date: "计算截止日",
  required_certificates: "所需证书", student_statuses: "允许的在读或毕业状态",
  MASTER: "硕士", BACHELOR: "本科", DOCTORATE: "博士", ASSOCIATE: "专科", SECONDARY: "中等教育",
};
export function readableValue(value: unknown): string {
  if (value == null) return "原文尚未明确说明";
  if (Array.isArray(value)) return value.map(readableValue).join("、");
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${words[k] ?? k}：${readableValue(v)}`).join("；");
  return words[String(value)] ?? String(value);
}

export function readableLocator(locator: Record<string, unknown>): string {
  const labels: Record<string, string> = { sheet: "工作表", row: "行", column: "列", page: "页", paragraph: "段落", projection_id: "位置", cell: "单元格" };
  return Object.entries(locator).filter(([k, v]) => labels[k] && ["string", "number"].includes(typeof v))
    .map(([k, v]) => `${labels[k]} ${v}`).join(" · ") || "展开原件核对上下文；当前没有可直接阅读的位置说明";
}
