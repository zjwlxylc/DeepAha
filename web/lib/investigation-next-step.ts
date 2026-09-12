import type { InvestigationTask } from "./investigations";

/**
 * Batch-3 navigation layer. Pure function that turns the *current* investigation
 * task view into an ordered list of "what to do next", derived only from fields
 * the backend already returns (`status`, `delivery_hash`, `document_preparation`,
 * `entity_binding`, `fact_review`, `rule_review`, `error_code`,
 * `dispatch_requested_at`). It never asks the operator to type an internal id.
 *
 * Known boundary (主理人裁定 §5-1): the task view does not expose the latest
 * condition-snapshot `plan_id`, so step 5 (跨层条件) and step 6 (范围预检) point
 * to in-page anchors rather than a direct `unit-plans/[planId]/...` link. The
 * direct link only becomes reachable through the existing "查看条件快照" entry
 * rendered inside the rule-review section after a snapshot exists.
 */

export type NextStepStatus = "ACTIONABLE" | "DONE" | "WAITING" | "BLOCKED";

export interface InvestigationNextStep {
  key: string;
  label: string;
  status: NextStepStatus;
  /** Non-empty whenever status is not ACTIONABLE; explains done / why n/a. */
  reason: string | null;
  /** In-page anchor to the section that carries the entry (no internal ids). */
  anchor: string;
  /** Optional absolute link when the task view already determines one. */
  href?: string;
}

const ANCHORS = {
  dispatch: "#investigation-dispatch",
  materials: "#investigation-materials-title",
  documents: "#investigation-documents-title",
  bindings: "#investigation-binding-title",
  facts: "#investigation-field-review-title",
  rules: "#investigation-rule-review-title",
} as const;

function step(
  key: string,
  label: string,
  status: NextStepStatus,
  reason: string | null,
  anchor: string,
  href?: string,
): InvestigationNextStep {
  // A non-actionable step must always explain itself; guard against accidental
  // blank copy so the UI never shows an unexplained "不适用".
  if (status !== "ACTIONABLE" && (reason === null || reason.trim() === "")) {
    throw new Error(`next-step ${key} requires an explicit reason when not actionable`);
  }
  return { key, label, status, reason, anchor, ...(href ? { href } : {}) };
}

/** Snapshot entry availability mirrors `unit-plan-form.tsx`'s `unresolved` rule. */
function snapshotEntryAvailable(task: InvestigationTask): boolean {
  const preparations = task.rule_review?.current ?? [];
  return preparations.some((prep) => {
    if (prep.target.target_scope !== "UNIT") return false;
    return !prep.rows.some((row) => row.rule_candidate_id
      && !["APPROVE", "REJECT"].includes(prep.decisions[row.rule_candidate_id]?.decision ?? ""));
  });
}

export function investigationNextSteps(task: InvestigationTask): InvestigationNextStep[] {
  const steps: InvestigationNextStep[] = [];
  const materialsCount = task.materials.length;
  const documentPrepared = task.document_preparation?.status === "PREPARED";
  const factReady = task.fact_review?.current != null;
  const rulesReady = (task.rule_review?.current?.length ?? 0) > 0;

  // 0 · 发起调查
  if (task.status === "QUEUED" && !task.dispatch_requested_at) {
    steps.push(step("dispatch", "发起调查", "ACTIONABLE", null, ANCHORS.dispatch));
  } else if (task.status === "QUEUED") {
    steps.push(step("dispatch", "发起调查", "WAITING",
      "已发起，等待处理进程在就绪后安排执行；无需重复发起。", ANCHORS.dispatch));
  } else if (["FAILED_PREPARATION", "FAILED_VALIDATION", "EXECUTION_UNCERTAIN", "COLLECTION_RETRYABLE", "EXPIRED"].includes(task.status)) {
    steps.push(step("dispatch", "发起调查", "BLOCKED",
      "调查失败或结果尚未确定；请查看任务错误与材料回收状态。", ANCHORS.dispatch));
  } else {
    steps.push(step("dispatch", "发起调查", "DONE",
      "本任务不在可发起状态；调查已推进或已结束，无需重复发起。", ANCHORS.dispatch));
  }

  // 1 · 回收原件
  if (materialsCount > 0) {
    steps.push(step("materials", "回收原件", "DONE",
      `已回收 ${materialsCount} 份原件，可在调查材料区查看与下载。`, ANCHORS.materials));
  } else {
    steps.push(step("materials", "回收原件", "WAITING",
      "尚未回收原件；请先发起并等待回收，或使用适用时的恢复入口。", ANCHORS.materials));
  }

  // 2 · 准备文档
  if (!task.delivery_hash) {
    steps.push(step("documents", "准备文档", "WAITING",
      "尚无材料版本，无法准备文档。", ANCHORS.documents));
  } else if (documentPrepared) {
    steps.push(step("documents", "准备文档", "DONE",
      "文档证据已准备；语义仍需人工核对。", ANCHORS.documents));
  } else {
    steps.push(step("documents", "准备文档", "ACTIONABLE", null, ANCHORS.documents));
  }

  // 3 · 绑定身份/岗位
  if (!documentPrepared) {
    steps.push(step("bindings", "绑定身份/岗位", "WAITING",
      "需先完成文档准备，才能登记身份/岗位。", ANCHORS.bindings));
  } else if (task.status !== "APPROVED") {
    steps.push(step("bindings", "绑定身份/岗位", "WAITING",
      "需先完成内部材料审核，批准材料后才能登记身份/岗位。", "#investigation-review-title"));
  } else if (task.entity_binding) {
    steps.push(step("bindings", "绑定身份/岗位", "DONE",
      "已完成机会与岗位归属确认；字段内容仍是候选。", ANCHORS.bindings));
  } else {
    steps.push(step("bindings", "绑定身份/岗位", "ACTIONABLE", null, ANCHORS.bindings));
  }

  // 4 · 字段与规则
  if (!task.entity_binding) {
    steps.push(step("facts", "字段与规则", "WAITING",
      "需先完成身份/岗位绑定，字段与规则才能落到明确目标。", ANCHORS.facts));
  } else if (factReady && rulesReady) {
    steps.push(step("facts", "字段与规则", "DONE",
      "字段事实与规则候选已整理；逐条批准不代表完整条件覆盖。", ANCHORS.facts));
  } else {
    steps.push(step("facts", "字段与规则", "ACTIONABLE", null, ANCHORS.facts));
  }

  // 5 · 跨层条件
  if (!rulesReady) {
    steps.push(step("cross-level", "跨层条件", "WAITING",
      "尚无已整理的规则条件，无法汇总跨层条件。", ANCHORS.rules));
  } else {
    steps.push(step("cross-level", "跨层条件", "ACTIONABLE", null, ANCHORS.rules));
  }

  // 6 · 范围预检
  if (snapshotEntryAvailable(task)) {
    steps.push(step("scope-preflight", "范围预检", "ACTIONABLE", null, ANCHORS.rules));
  } else {
    steps.push(step("scope-preflight", "范围预检", "WAITING",
      "需先整理条件快照，才能运行范围预检。", ANCHORS.rules));
  }

  return steps;
}
